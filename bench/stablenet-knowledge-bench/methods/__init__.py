# methods package — context-provision method dispatchers for CKG Benchmark.
#
# M1_raw:       raw file contents from citation anchors (oracle baseline)
# M1_fair:      keyword-search file selection from prompt only (non-oracle baseline)
# M2_graph_full: graph full dump via get_subgraph(depth=2, max_total=2000)
# M3_incremental: incremental multi-turn cks tool loop
# M4_get_for_task: single get_for_task() EvidencePack
from .m1_raw_files import M1RawFiles
from .m1_fair_files import M1FairFiles
from .m2_graph_full import M2GraphFull
from .m3_incremental import M3Incremental
from .m4_get_for_task import M4GetForTask

__all__ = ["M1RawFiles", "M1FairFiles", "M2GraphFull", "M3Incremental", "M4GetForTask"]

METHOD_REGISTRY = {
    "M1_raw": M1RawFiles,
    "M1_fair": M1FairFiles,
    "M2_graph_full": M2GraphFull,
    "M3_incremental": M3Incremental,
    "M4_get_for_task": M4GetForTask,
}
