# Data Ingestion Challenges

## What we Built | Value to the Business

**Unified Ingestion Layer:** Three incompatible source systems — CSV orders, JSON customers, and a SQL products database — are each handled by a dedicated module that normalises everything into the same format before any processing begins.
| **Consistency:** Analysts always work from a single, unified data model regardless of which source system the data came from.

**Stage Isolation:** Each source ingests independently. If the products database goes down, orders and customers still complete successfully — one failure does not cascade.
| **Resilience:** A single unavailable source no longer takes down the entire pipeline or delays downstream reports that don't depend on it.

**Pre-Run Source Check:** Before the pipeline writes a single record, it verifies that all three sources are reachable. If anything is missing, it stops immediately with a clear error.
| **Reliability:** Operators know within seconds of a run starting whether a source is unavailable — not hours later when reports look wrong.

---

## Speaker Notes

**Unified Landing Layer**
NovaCart's source data comes in three completely different formats — orders as CSV files, customers as nested JSON, and products out of a SQL database. Rather than forcing those systems to change, we built a dedicated module for each one that handles its native format and normalises the output. By the time data moves to the next stage, it's all in the same shape — so analysts are always working from one consistent model, not three.

**Stage Isolation**
What makes this design particularly valuable is that each source runs independently. If the products database goes down, orders and customers still complete. NovaCart had experienced full pipeline failures before — one broken source taking everything down with it. That no longer happens here.

**Pre-Run Source Check**
Before the pipeline touches anything, it now checks that all three sources are actually there. If one is missing, it stops immediately with a clear message pointing at exactly what's wrong — rather than failing silently mid-run and leaving operators to figure out why the reports look off hours later.
