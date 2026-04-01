from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple, Union


class SegFault(RuntimeError):
    """Raised when a process touches an unmapped or invalid virtual page."""


@dataclass(frozen=True)
class PhysicalPageInfo:
    bank: int
    block: int


@dataclass(frozen=True)
class TLBEntry:
    pid: int
    vpage: int


PageEntry = Union[PhysicalPageInfo, int]  # int == swap slot


class MemoryManager:
    """
    Real memory table / virtual-memory core.

    Features:
      - physical RAM backed by banks -> blocks -> bytearrays
      - physical allocation table with ownership / dirty / refcount tracking
      - process table
      - per-process virtual page table
      - swap backing store
      - TLB
      - copy-on-write private page promotion
      - snapshot save/load
      - high-level JSON / bytes / string object storage
    """

    def __init__(
        self,
        num_banks: int = 4,
        blocks_per_bank: int = 64,
        block_size: int = 64,
        tlb_capacity: int = 16,
        tlb_miss_latency: int = 5,
        swap_path: str = "swap.bin",
        max_swap_pages: int = 256,
    ) -> None:
        self.num_banks = num_banks
        self.blocks_per_bank = blocks_per_bank
        self.block_size = block_size
        self.tlb_capacity = tlb_capacity
        self.tlb_miss_latency = tlb_miss_latency
        self.cache_latency = tlb_miss_latency  # compatibility with earlier patch naming
        self.last_tlb_latency = 0

        # Physical RAM
        self.ram: List[List[bytearray]] = [
            [bytearray(block_size) for _ in range(blocks_per_bank)]
            for _ in range(num_banks)
        ]

        # Physical allocation table
        self.table: Dict[str, Dict[str, Any]] = {}
        self._free_list: Deque[str] = deque()
        for bank in range(num_banks):
            for block in range(blocks_per_bank):
                key = self._indices_to_key(bank, block)
                self.table[key] = {
                    "allocated": False,
                    "owner": None,
                    "pid": None,
                    "size_used": 0,
                    "dirty": False,
                    "refcount": 0,
                }
                self._free_list.append(key)

        # Resident-page LRU tracking
        self._lru: Deque[Tuple[int, int]] = deque()

        # Process / page tables
        self._process_table: Dict[int, str] = {}
        self._page_table: Dict[int, Dict[int, PageEntry]] = {}
        self._next_pid = 100

        # Kernel-owned object registry
        self._objects: Dict[str, Dict[str, int]] = {}

        # TLB
        self.tlb: OrderedDict[TLBEntry, PhysicalPageInfo] = OrderedDict()

        # Swap
        self.swap_path = swap_path
        self.max_swap_pages = max_swap_pages
        self._swap_free: Deque[int] = deque(range(max_swap_pages))
        self._swap_refcount: Dict[int, int] = {}
        self._swap_file = None
        self._open_swap_file()

        # Kernel process
        self.kernel_pid = self.create_process("__kernel__")

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def _indices_to_key(self, bank: int, block: int) -> str:
        return f"b{bank}_blk{block}"

    def _key_to_indices(self, key: str) -> Tuple[int, int]:
        bank_part, block_part = key.split("_")
        return int(bank_part[1:]), int(block_part[3:])

    def _touch_lru(self, bank: int, block: int) -> None:
        try:
            self._lru.remove((bank, block))
        except ValueError:
            pass
        self._lru.append((bank, block))

    def _invalidate_tlb_page(self, pid: int, vpage: int) -> None:
        self.tlb.pop(TLBEntry(pid, vpage), None)

    def _tlb_touch(self, pid: int, vpage: int, phys: PhysicalPageInfo) -> None:
        key = TLBEntry(pid, vpage)
        if key in self.tlb:
            self.tlb.move_to_end(key)
            self.tlb[key] = phys
            return
        if len(self.tlb) >= self.tlb_capacity:
            self.tlb.popitem(last=False)
        self.tlb[key] = phys

    def _rebuild_free_list(self) -> None:
        self._free_list = deque(
            key
            for bank in range(self.num_banks)
            for block in range(self.blocks_per_bank)
            for key in [self._indices_to_key(bank, block)]
            if not self.table[key]["allocated"]
        )

    def _alloc_swap_slot(self, refcount: int = 1) -> int:
        if not self._swap_free:
            raise MemoryError("Swap full")
        slot = self._swap_free.popleft()
        self._swap_refcount[slot] = int(refcount)
        return slot

    def _inc_swap_ref(self, slot: int) -> None:
        self._swap_refcount[slot] = int(self._swap_refcount.get(slot, 0)) + 1
        try:
            self._swap_free.remove(slot)
        except ValueError:
            pass

    def _dec_swap_ref(self, slot: int) -> None:
        current = int(self._swap_refcount.get(slot, 0))
        if current <= 0:
            if slot not in self._swap_free:
                self._swap_free.append(slot)
            self._swap_refcount.pop(slot, None)
            return
        new_ref = current - 1
        if new_ref == 0:
            self._swap_refcount.pop(slot, None)
            if slot not in self._swap_free:
                self._swap_free.append(slot)
        else:
            self._swap_refcount[slot] = new_ref

    # ------------------------------------------------------------------
    # Swap
    # ------------------------------------------------------------------
    def _open_swap_file(self) -> None:
        """
        Open or create the backing swap file.

        Important: do not destructively truncate an existing file just because the
        current manager instance was created with placeholder dimensions before a
        later load_snapshot(). We only guarantee the file is *at least* the size
        needed for the current configuration.
        """
        expected_size = self.max_swap_pages * self.block_size
        parent = os.path.dirname(os.path.abspath(self.swap_path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        mode = "r+b" if os.path.exists(self.swap_path) else "w+b"
        self._swap_file = open(self.swap_path, mode)
        self._swap_file.seek(0, os.SEEK_END)
        current_size = self._swap_file.tell()
        if current_size < expected_size and expected_size > 0:
            self._swap_file.seek(expected_size - 1)
            self._swap_file.write(b"\x00")
        self._swap_file.flush()

    def _swap_write(self, slot: int, data: bytes) -> None:
        if len(data) != self.block_size:
            raise ValueError("swap write size must equal block_size")
        self._swap_file.seek(slot * self.block_size)
        self._swap_file.write(data)
        self._swap_file.flush()

    def _swap_read(self, slot: int) -> bytes:
        self._swap_file.seek(slot * self.block_size)
        data = self._swap_file.read(self.block_size)
        if len(data) != self.block_size:
            raise RuntimeError("short read from swap")
        return data

    # ------------------------------------------------------------------
    # Physical allocation table
    # ------------------------------------------------------------------
    def _alloc_phys_block(self, pid: int) -> PhysicalPageInfo:
        if not self._free_list:
            self._evict_one_page()
        if not self._free_list:
            raise MemoryError("Out of physical memory and no evictable page")

        key = self._free_list.popleft()
        bank, block = self._key_to_indices(key)
        self.ram[bank][block][:] = b"\x00" * self.block_size
        self.table[key].update(
            {
                "allocated": True,
                "owner": self._process_table[pid],
                "pid": pid,
                "size_used": 0,
                "dirty": False,
                "refcount": 1,
            }
        )
        self._touch_lru(bank, block)
        return PhysicalPageInfo(bank, block)

    def _release_phys_key(self, key: str) -> None:
        bank, block = self._key_to_indices(key)
        self.ram[bank][block][:] = b"\x00" * self.block_size
        self.table[key].update(
            {
                "allocated": False,
                "owner": None,
                "pid": None,
                "size_used": 0,
                "dirty": False,
                "refcount": 0,
            }
        )
        if key not in self._free_list:
            self._free_list.append(key)
        try:
            self._lru.remove((bank, block))
        except ValueError:
            pass

    def _inc_ref(self, key: str) -> None:
        self.table[key]["refcount"] = int(self.table[key]["refcount"]) + 1

    def _dec_ref(self, key: str) -> None:
        new_ref = int(self.table[key]["refcount"]) - 1
        if new_ref < 0:
            raise RuntimeError(f"Negative refcount for {key}")
        self.table[key]["refcount"] = new_ref
        if new_ref == 0:
            self._release_phys_key(key)

    def _find_owner_mapping(self, bank: int, block: int) -> Optional[Tuple[int, int]]:
        mappings = self._find_all_mappings(bank, block)
        return mappings[0] if mappings else None

    def _find_all_mappings(self, bank: int, block: int) -> List[Tuple[int, int]]:
        owners: List[Tuple[int, int]] = []
        for pid, pt in self._page_table.items():
            for vpage, entry in pt.items():
                if isinstance(entry, PhysicalPageInfo) and entry.bank == bank and entry.block == block:
                    owners.append((pid, vpage))
        return owners

    def _evict_one_page(self) -> None:
        if not self._lru:
            raise MemoryError("No resident page available for eviction")

        original_len = len(self._lru)
        scanned = 0
        while scanned < original_len:
            bank, block = self._lru.popleft()
            scanned += 1
            key = self._indices_to_key(bank, block)
            meta = self.table[key]

            if not meta["allocated"]:
                continue

            owners = self._find_all_mappings(bank, block)
            if not owners:
                self._release_phys_key(key)
                return

            slot = self._alloc_swap_slot(refcount=len(owners))
            self._swap_write(slot, bytes(self.ram[bank][block]))
            for owner_pid, owner_vpage in owners:
                self._page_table[owner_pid][owner_vpage] = slot
                self._invalidate_tlb_page(owner_pid, owner_vpage)
            self._release_phys_key(key)
            return

        raise MemoryError("No evictable page found")

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------
    def create_process(self, name: str) -> int:
        pid = self._next_pid
        self._next_pid += 1
        self._process_table[pid] = name
        self._page_table[pid] = {}
        return pid

    def destroy_process(self, pid: int) -> None:
        if pid not in self._process_table:
            return
        pt = self._page_table.get(pid, {})
        for vpage, entry in list(pt.items()):
            self._invalidate_tlb_page(pid, vpage)
            if isinstance(entry, PhysicalPageInfo):
                key = self._indices_to_key(entry.bank, entry.block)
                self._dec_ref(key)
            else:
                self._dec_swap_ref(entry)
        self._page_table.pop(pid, None)
        self._process_table.pop(pid, None)

    def fork(self, parent_pid: int, child_name: Optional[str] = None) -> int:
        if parent_pid not in self._process_table:
            raise ValueError(f"Unknown parent PID {parent_pid}")

        child_pid = self.create_process(child_name or f"{self._process_table[parent_pid]}_child")
        for vpage in sorted(self._page_table[parent_pid].keys()):
            entry = self._page_table[parent_pid][vpage]
            if isinstance(entry, PhysicalPageInfo):
                key = self._indices_to_key(entry.bank, entry.block)
                self._inc_ref(key)
                self._page_table[child_pid][vpage] = entry
            else:
                self._inc_swap_ref(entry)
                self._page_table[child_pid][vpage] = entry
        return child_pid

    # ------------------------------------------------------------------
    # Virtual allocation
    # ------------------------------------------------------------------
    def _next_free_vpage(self, pid: int, n_pages: int = 1) -> int:
        pt = self._page_table[pid]
        if not pt:
            return 0

        used = sorted(pt.keys())
        candidate = 0
        for vpage in used:
            if vpage - candidate >= n_pages:
                return candidate
            if vpage >= candidate:
                candidate = vpage + 1
        return candidate

    def vmalloc(self, pid: int, n_pages: int) -> int:
        if pid not in self._process_table:
            raise ValueError(f"Unknown PID {pid}")
        if n_pages <= 0:
            raise ValueError("n_pages must be > 0")

        start_vpage = self._next_free_vpage(pid, n_pages)
        for i in range(n_pages):
            vpage = start_vpage + i
            phys = self._alloc_phys_block(pid)
            self._page_table[pid][vpage] = phys
            self._invalidate_tlb_page(pid, vpage)
        return start_vpage * self.block_size

    def vfree(self, pid: int, vaddr: int, n_pages: int) -> None:
        if pid not in self._page_table:
            return
        start_vpage = vaddr // self.block_size
        for i in range(n_pages):
            vpage = start_vpage + i
            entry = self._page_table[pid].pop(vpage, None)
            self._invalidate_tlb_page(pid, vpage)
            if entry is None:
                continue
            if isinstance(entry, PhysicalPageInfo):
                key = self._indices_to_key(entry.bank, entry.block)
                self._dec_ref(key)
            else:
                self._dec_swap_ref(entry)

    # ------------------------------------------------------------------
    # Paging / translation
    # ------------------------------------------------------------------
    def _page_in(self, pid: int, vpage: int, slot: int) -> PhysicalPageInfo:
        phys = self._alloc_phys_block(pid)
        self.ram[phys.bank][phys.block][:] = self._swap_read(slot)
        self.table[self._indices_to_key(phys.bank, phys.block)]["size_used"] = self.block_size
        self._page_table[pid][vpage] = phys
        self._dec_swap_ref(slot)
        return phys

    def _translate(self, pid: int, vaddr: int) -> Tuple[PhysicalPageInfo, int, int]:
        vpage, offset = divmod(vaddr, self.block_size)
        tlb_key = TLBEntry(pid, vpage)

        if tlb_key in self.tlb:
            phys = self.tlb[tlb_key]
            self.tlb.move_to_end(tlb_key)
            self._touch_lru(phys.bank, phys.block)
            return phys, offset, 0

        if pid not in self._process_table:
            raise SegFault(f"PID {pid} does not exist")

        proc_pt = self._page_table[pid]
        if vpage not in proc_pt:
            raise SegFault(f"Process {pid} has no mapping for page {vpage}")

        entry = proc_pt[vpage]
        if isinstance(entry, PhysicalPageInfo):
            phys = entry
        else:
            phys = self._page_in(pid, vpage, entry)

        self._touch_lru(phys.bank, phys.block)
        self._tlb_touch(pid, vpage, phys)
        return phys, offset, self.tlb_miss_latency

    def _ensure_private_page(self, pid: int, vpage: int, phys: PhysicalPageInfo) -> PhysicalPageInfo:
        key = self._indices_to_key(phys.bank, phys.block)
        if int(self.table[key]["refcount"]) <= 1:
            return phys

        new_phys = self._alloc_phys_block(pid)
        self.ram[new_phys.bank][new_phys.block][:] = self.ram[phys.bank][phys.block][:]
        new_key = self._indices_to_key(new_phys.bank, new_phys.block)
        self.table[new_key]["size_used"] = self.table[key]["size_used"]
        self.table[new_key]["dirty"] = self.table[key]["dirty"]

        self._dec_ref(key)
        self._page_table[pid][vpage] = new_phys
        self._invalidate_tlb_page(pid, vpage)
        self._tlb_touch(pid, vpage, new_phys)
        return new_phys

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------
    def vread(self, pid: int, vaddr: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must be >= 0")

        remaining = size
        cur_addr = vaddr
        out = bytearray()
        self.last_tlb_latency = 0

        while remaining:
            phys, offset, latency = self._translate(pid, cur_addr)
            if latency:
                self.last_tlb_latency = latency

            available = self.block_size - offset
            chunk = min(available, remaining)
            out.extend(self.ram[phys.bank][phys.block][offset : offset + chunk])

            cur_addr += chunk
            remaining -= chunk

        return bytes(out)

    def vwrite(self, pid: int, vaddr: int, data: bytes) -> None:
        remaining = len(data)
        cur_addr = vaddr
        written = 0
        self.last_tlb_latency = 0

        while remaining:
            phys, offset, latency = self._translate(pid, cur_addr)
            if latency:
                self.last_tlb_latency = latency

            vpage = cur_addr // self.block_size
            phys = self._ensure_private_page(pid, vpage, phys)

            available = self.block_size - offset
            chunk = min(available, remaining)
            self.ram[phys.bank][phys.block][offset : offset + chunk] = data[written : written + chunk]

            key = self._indices_to_key(phys.bank, phys.block)
            self.table[key]["dirty"] = True
            self.table[key]["size_used"] = max(int(self.table[key]["size_used"]), offset + chunk)

            cur_addr += chunk
            written += chunk
            remaining -= chunk

    # ------------------------------------------------------------------
    # High-level stored bytes / strings / objects
    # ------------------------------------------------------------------
    def store_bytes(self, pid: int, payload: bytes) -> int:
        packet = len(payload).to_bytes(4, "little") + payload
        pages = ceil(len(packet) / self.block_size)
        addr = self.vmalloc(pid, pages)
        self.vwrite(pid, addr, packet)
        return addr

    def load_bytes(self, pid: int, addr: int) -> bytes:
        length = int.from_bytes(self.vread(pid, addr, 4), "little")
        return self.vread(pid, addr + 4, length)

    def store_string(self, pid: int, text: str) -> int:
        return self.store_bytes(pid, text.encode("utf-8"))

    def load_string(self, pid: int, addr: int) -> str:
        return self.load_bytes(pid, addr).decode("utf-8")

    def _pages_for_stored_addr(self, pid: int, addr: int) -> int:
        length = int.from_bytes(self.vread(pid, addr, 4), "little")
        total = 4 + length
        return ceil(total / self.block_size)

    def free_stored_addr(self, pid: int, addr: int) -> None:
        self.vfree(pid, addr, self._pages_for_stored_addr(pid, addr))

    def put_json_object(self, key: str, value: Any, pid: Optional[int] = None) -> int:
        """
        Atomically replace a logical object mapping from the caller's point of view:
        we write the new object first, then flip the registry entry, then free the old one.
        If the new write fails, the old mapping stays intact.
        """
        if pid is None:
            pid = self.kernel_pid

        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        new_addr = self.store_bytes(pid, payload)
        old = self._objects.get(key)
        self._objects[key] = {"pid": pid, "addr": new_addr}

        if old is not None:
            try:
                self.free_stored_addr(int(old["pid"]), int(old["addr"]))
            except Exception:
                # Keep the new mapping even if cleanup of the old storage fails.
                pass

        return new_addr

    def get_json_object(self, key: str, default: Any = None) -> Any:
        meta = self._objects.get(key)
        if not meta:
            return default
        try:
            raw = self.load_bytes(int(meta["pid"]), int(meta["addr"]))
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return default

    def delete_object(self, key: str) -> None:
        meta = self._objects.pop(key, None)
        if not meta:
            return
        self.free_stored_addr(int(meta["pid"]), int(meta["addr"]))

    def list_object_keys(self, prefix: str = "") -> List[str]:
        if not prefix:
            return sorted(self._objects.keys())
        return sorted(k for k in self._objects.keys() if k.startswith(prefix))

    # ------------------------------------------------------------------
    # Snapshot save/load
    # ------------------------------------------------------------------
    def save_snapshot(self, base_path: str) -> None:
        """
        Write a self-contained snapshot set and commit it by replacing the metadata
        file last. The metadata points at versioned RAM/swap payload files so a
        crash during save does not leave a mixed fixed-name snapshot set.
        """
        base = Path(base_path)
        directory = base.parent if str(base.parent) != "" else Path(".")
        directory.mkdir(parents=True, exist_ok=True)
        meta_path = Path(str(base_path) + ".meta.json")
        previous_meta: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                previous_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                previous_meta = {}

        stamp = f"{time.time_ns()}_{os.getpid()}"
        ram_name = f"{base.name}.{stamp}.ram"
        swap_name = f"{base.name}.{stamp}.swap"
        ram_path = directory / ram_name
        swap_snapshot_path = directory / swap_name
        meta_tmp = directory / f".{base.name}.{stamp}.meta.tmp"

        self._swap_file.flush()
        try:
            os.fsync(self._swap_file.fileno())
        except OSError:
            pass

        with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, prefix=f".{base.name}.{stamp}.", suffix=".ram.tmp") as f:
            ram_tmp_path = Path(f.name)
            for bank in self.ram:
                for block in bank:
                    f.write(block)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(ram_tmp_path, ram_path)

        if os.path.abspath(self.swap_path) != os.path.abspath(str(swap_snapshot_path)):
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, prefix=f".{base.name}.{stamp}.", suffix=".swap.tmp") as f:
                swap_tmp_path = Path(f.name)
            shutil.copyfile(self.swap_path, swap_tmp_path)
            os.replace(swap_tmp_path, swap_snapshot_path)
        else:
            self._swap_file.flush()
            try:
                os.fsync(self._swap_file.fileno())
            except OSError:
                pass

        page_table_dump: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for pid, pt in self._page_table.items():
            page_table_dump[str(pid)] = {}
            for vpage, entry in pt.items():
                if isinstance(entry, PhysicalPageInfo):
                    page_table_dump[str(pid)][str(vpage)] = {
                        "kind": "phys",
                        "bank": entry.bank,
                        "block": entry.block,
                    }
                else:
                    page_table_dump[str(pid)][str(vpage)] = {
                        "kind": "swap",
                        "slot": entry,
                    }

        meta = {
            "num_banks": self.num_banks,
            "blocks_per_bank": self.blocks_per_bank,
            "block_size": self.block_size,
            "tlb_capacity": self.tlb_capacity,
            "tlb_miss_latency": self.tlb_miss_latency,
            "max_swap_pages": self.max_swap_pages,
            "table": self.table,
            "process_table": self._process_table,
            "page_table": page_table_dump,
            "next_pid": self._next_pid,
            "kernel_pid": self.kernel_pid,
            "objects": self._objects,
            "lru": list(self._lru),
            "ram_snapshot": ram_name,
            "swap_snapshot": swap_name,
        }

        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(meta_tmp, meta_path)

        for old_name in (previous_meta.get("ram_snapshot"), previous_meta.get("swap_snapshot")):
            if not old_name or old_name in {ram_name, swap_name}:
                continue
            old_path = directory / str(old_name)
            try:
                if old_path.exists():
                    old_path.unlink()
            except OSError:
                pass

    def load_snapshot(self, base_path: str) -> bool:
        base = Path(base_path)
        meta_path = Path(str(base_path) + ".meta.json")
        legacy_ram = Path(str(base_path) + ".ram")
        legacy_swap = Path(str(base_path) + ".swap")
        if not meta_path.exists():
            return False

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        directory = meta_path.parent
        ram_name = meta.get("ram_snapshot")
        swap_name = meta.get("swap_snapshot")
        ram_path = (directory / str(ram_name)) if ram_name else legacy_ram
        swap_snapshot_path = (directory / str(swap_name)) if swap_name else legacy_swap
        if not (ram_path.exists() and swap_snapshot_path.exists()):
            return False

        self.num_banks = int(meta["num_banks"])
        self.blocks_per_bank = int(meta["blocks_per_bank"])
        self.block_size = int(meta["block_size"])
        self.tlb_capacity = int(meta["tlb_capacity"])
        self.tlb_miss_latency = int(meta["tlb_miss_latency"])
        self.cache_latency = self.tlb_miss_latency
        self.max_swap_pages = int(meta["max_swap_pages"])

        try:
            if self._swap_file is not None:
                self._swap_file.close()
        except Exception:
            pass
        self.swap_path = str(swap_snapshot_path)
        self._swap_free = deque(range(self.max_swap_pages))
        self._swap_refcount = {}
        self._open_swap_file()

        self.ram = [
            [bytearray(self.block_size) for _ in range(self.blocks_per_bank)]
            for _ in range(self.num_banks)
        ]
        with open(ram_path, "rb") as f:
            for bank in range(self.num_banks):
                for block in range(self.blocks_per_bank):
                    data = f.read(self.block_size)
                    if len(data) != self.block_size:
                        raise RuntimeError("Corrupt RAM snapshot")
                    self.ram[bank][block][:] = data

        self.table = meta["table"]
        self._process_table = {int(k): v for k, v in meta["process_table"].items()}
        self._next_pid = int(meta["next_pid"])
        self.kernel_pid = int(meta["kernel_pid"])
        self._objects = {
            k: {"pid": int(v["pid"]), "addr": int(v["addr"])}
            for k, v in meta["objects"].items()
        }
        self._lru = deque(tuple(item) for item in meta.get("lru", []))

        self._page_table = {}
        used_swap_slots: Dict[int, int] = {}
        for pid_s, pt in meta["page_table"].items():
            pid = int(pid_s)
            self._page_table[pid] = {}
            for vpage_s, entry in pt.items():
                vpage = int(vpage_s)
                if entry["kind"] == "phys":
                    self._page_table[pid][vpage] = PhysicalPageInfo(
                        int(entry["bank"]),
                        int(entry["block"]),
                    )
                else:
                    slot = int(entry["slot"])
                    used_swap_slots[slot] = used_swap_slots.get(slot, 0) + 1
                    self._page_table[pid][vpage] = slot

        self._swap_refcount = dict(used_swap_slots)
        self._swap_free = deque(slot for slot in range(self.max_swap_pages) if slot not in used_swap_slots)
        self._rebuild_free_list()
        self.tlb.clear()
        self.last_tlb_latency = 0
        return True

    def close(self) -> None:
        try:
            if self._swap_file is not None:
                self._swap_file.flush()
                self._swap_file.close()
        except Exception:
            pass
        finally:
            self._swap_file = None

    # ------------------------------------------------------------------
    # Debug / reporting
    # ------------------------------------------------------------------
    def fragmentation_report(self) -> str:
        total = self.num_banks * self.blocks_per_bank
        free = len(self._free_list)
        used = total - free
        return f"Memory: {used}/{total} blocks used, {free} free"

    def tlb_dump(self) -> str:
        if not self.tlb:
            return "(TLB empty)"
        lines = []
        for entry, phys in self.tlb.items():
            lines.append(
                f"pid={entry.pid} vpage={entry.vpage} -> bank={phys.bank} block={phys.block}"
            )
        return "\n".join(lines)


class MemoryBackedAppState:
    def __init__(self, mem: MemoryManager, object_key: str = "__terminal_app_state__") -> None:
        self.mem = mem
        self.object_key = object_key
        self.data: Dict[str, Any] = {}

    def load(self) -> None:
        loaded = self.mem.get_json_object(self.object_key, default={})
        self.data.clear()
        if isinstance(loaded, dict):
            self.data.update(loaded)

    def sync(self) -> None:
        self.mem.put_json_object(self.object_key, self.data)

    def clear(self) -> None:
        self.data.clear()


def attach_memory_manager(app: Any, snapshot_base: Optional[str] = None) -> None:
    """
    Glue MemoryManager into a TerminalApp-style object.

    Expected app attributes/methods:
      - data_file (optional)
      - handle_action(action)
      - save_data()
      - load_data()
    """
    base = snapshot_base
    if base is None:
        raw = getattr(app, "data_file", None) or "terminal_memory"
        base = os.path.splitext(raw)[0]

    base_path = Path(base)
    base_dir = base_path.parent if str(base_path.parent) != "" else Path(".")
    base_dir.mkdir(parents=True, exist_ok=True)

    mem = MemoryManager(swap_path=str(base_path) + ".swap")
    loaded = mem.load_snapshot(base)

    app.mem = mem
    app.app_state = MemoryBackedAppState(mem)
    initial_data = dict(getattr(app, "app_data", {}) or {})
    if loaded:
        app.app_state.load()
    else:
        app.app_state.clear()
        if initial_data:
            app.app_state.data.update(initial_data)
        app.app_state.sync()

    app.app_data = app.app_state.data

    def save_data() -> None:
        app.app_state.sync()
        app.mem.save_snapshot(base)
        if hasattr(app, "status_msg"):
            app.status_msg = "Saved."
        if hasattr(app, "_needs_render"):
            app._needs_render = True

    def load_data() -> None:
        if app.mem.load_snapshot(base):
            app.app_state.load()
            if hasattr(app, "status_msg"):
                app.status_msg = "Loaded saved data."
        else:
            app.app_state.clear()
            app.app_state.sync()
            if hasattr(app, "status_msg"):
                app.status_msg = "New Session."
        app.app_data = app.app_state.data
        if hasattr(app, "_needs_render"):
            app._needs_render = True

    original_handle_action = app.handle_action

    def handle_action_with_sync(action: Any) -> None:
        try:
            original_handle_action(action)
        finally:
            app.app_state.sync()

    app.save_data = save_data
    app.load_data = load_data
    app.handle_action = handle_action_with_sync
