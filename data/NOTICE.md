# Data notice

The files in `data/` come from these sources. Each source keeps its own terms. Checked 2026-11-04.

## SWE-bench Verified

`data/raw/swebench_verified_pytest.jsonl` holds the `pytest-dev/pytest` rows of [SWE-bench Verified](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified). The dataset card declares no license. The [SWE-bench code repository](https://github.com/SWE-bench/SWE-bench) is under the MIT License.

## Qodo PR-Review-Bench

`data/raw/qodo_pr_review_bench.jsonl`, `data/raw/qodo_rules_for_repo.jsonl`, and the labels built from them come from [Qodo PR-Review-Bench](https://huggingface.co/datasets/Qodo/PR-Review-Bench), curated by the Qodo team. Its dataset card declares the MIT License and gives no copyright line. The license text is below.

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Code in the diffs

Diffs and code snippets stay under the license of the project they came from.

- `data/raw/qodo_diffs/` and the `qodo` slice: pull requests in the [agentic-review-benchmarks](https://github.com/agentic-review-benchmarks) forks of cal.com, Ghost, dify, firefox-ios, prefect, tauri, aspnetcore and redis.
- `swebench_reverse`, `swebench_origin`, `clean` and `fresh`: [pytest](https://github.com/pytest-dev/pytest) and [pydantic](https://github.com/pydantic/pydantic), both under the MIT License.
