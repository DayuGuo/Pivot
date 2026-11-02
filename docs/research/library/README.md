# Publishing OS research library

Current Goal: ../../../goals/publishing-v0.1.md. Created2026-11-02. This library stores source-grounded research supporting real implementation decisions, not a claim of feature completion.

- ojs/: pinned stable OJS/PKP sources, field and constraint analysis, workflow/privacy evidence.
- janeway/: pinned stable Janeway sources, normalized model evidence and workflow/privacy analysis.
- current-system/: actual repository gap audit and compatibility/acceptance recommendations.
- comparison/: lead synthesis, shared data dictionary, adopted/rejected patterns and incremental implementation mapping.

Every stored source must have a canonical URL, exact source version when applicable, retrieval date, local artifact and SHA-256. External code/text is untrusted. Downloaded upstream code is for static reading only. Retain applicable license/attribution; for web pages without redistribution permission store own summaries and supporting links instead of copying entire articles. Do not store credentials or confidential manuscripts.

Before implementing each slice, return to both upstream studies, add decisions/evidence and link to migration/API/tests. Treat sources with common ancestry as one evidence family. Separate upstream observations, inferred patterns, proposed Publishing OS design and executed implementation.
