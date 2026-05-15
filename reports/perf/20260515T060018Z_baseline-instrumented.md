# ma3 search performance benchmark: baseline-instrumented

- generated_at: 2026-05-15T06:00:18.919812+00:00
- base_url: `http://127.0.0.1:18180`

| request | route | n | avg ms | p50 ms | p95 ms | max ms | statuses | avg results | errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| search_broad_observability | `/search` | 20 | 395.298 | 391.502 | 424.194 | 431.587 | `{"200": 20}` | 5 | 0 |
| search_client_upgrade | `/search` | 20 | 429.142 | 423.706 | 459.942 | 469.022 | `{"200": 20}` | 5 | 0 |
| search_ltp_mpi_rdma | `/search` | 20 | 311.521 | 304.24 | 340.307 | 342.766 | `{"200": 20}` | 5 | 0 |
| search_ma3_deploy_ltp | `/search` | 20 | 447.591 | 439.098 | 478.279 | 483.119 | `{"200": 20}` | 5 | 0 |
| search_zero_result | `/search` | 20 | 4485.189 | 4416.786 | 4804.078 | 4838.642 | `{"200": 20}` | 3 | 0 |
| v2_context_client_upgrade | `/v2/agent/context` | 20 | 448.659 | 438.396 | 482.372 | 487.288 | `{"200": 20}` | 7 | 0 |
| v2_context_ma3_deploy | `/v2/agent/context` | 20 | 466.058 | 460.365 | 508.591 | 510.731 | `{"200": 20}` | 7 | 0 |
| v2_explain_mpi_rdma | `/v2/search/explain` | 20 | 331.299 | 329.352 | 352.428 | 361.303 | `{"200": 20}` | 5 | 0 |
