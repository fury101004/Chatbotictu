# Current Test Results

- Generated at: `2026-06-14T01:57:00+07:00`
- Collect-only: **195 tests collected**
- Full suite: **194 passed, 0 failed, 1 skipped, 4 warnings**
- Graduation acceptance: **29 passed, 0 failed, 0 skipped, 166 deselected**

## Commands

```powershell
.\venv\Scripts\python.exe -m pytest --collect-only -q
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m pytest -m graduation_acceptance -q
```

The skipped test is the live LLM end-to-end test. The warnings are JWT HMAC key-length warnings from the local test configuration.
