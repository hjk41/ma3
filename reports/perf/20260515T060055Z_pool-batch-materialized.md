# ma3 search performance benchmark: pool-batch-materialized

- generated_at: 2026-05-15T06:00:55.409639+00:00
- base_url: `http://127.0.0.1:18180`

| request | route | n | avg ms | p50 ms | p95 ms | max ms | statuses | avg results | errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| search_broad_observability | `/search` | 20 | 10.58 | 9.897 | 10.094 | 31.302 | `{"200": 20}` | 5 | 0 |
| search_client_upgrade | `/search` | 20 | 9.891 | 10.33 | 10.479 | 10.574 | `{"200": 20}` | 5 | 0 |
| search_ltp_mpi_rdma | `/search` | 20 | 10.132 | 10.529 | 10.701 | 10.726 | `{"200": 20}` | 5 | 0 |
| search_ma3_deploy_ltp | `/search` | 20 | 10.84 | 11.201 | 11.801 | 12.194 | `{"200": 20}` | 5 | 0 |
| search_zero_result | `/search` | 20 | 45.19 | 43.252 | 62.026 | 67.206 | `{"200": 20}` | 3 | 0 |
| v2_context_client_upgrade | `/v2/agent/context` | 20 | 13.145 | 12.795 | 13.068 | 31.257 | `{"200": 20}` | 7 | 0 |
| v2_context_ma3_deploy | `/v2/agent/context` | 20 | 13.144 | 13.691 | 14.015 | 14.186 | `{"200": 20}` | 7 | 0 |
| v2_explain_mpi_rdma | `/v2/search/explain` | 20 | 13.641 | 13.319 | 13.922 | 32.122 | `{"200": 20}` | 5 | 0 |
