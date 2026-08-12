# Definition of done

last_reviewed: 2026-08-11

A source change is complete when targeted and full quality gates pass and the
public CLI and agent contracts agree. A fleet behavior change additionally
requires a fresh scoped execution, replay, feed publication, and Pronto
readback. Installed `qr` behavior must be reloaded or reinstalled before it is
claimed; otherwise the live behavior claim remains blocked.
