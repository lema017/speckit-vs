# Real test reports

What these runners wrote when they ran the tests in `sources/`, with the Spring Boot 3.3 and TypeScript 5.6 project around them:

| Directory | Runner | Configuration |
|---|---|---|
| `surefire/` | Maven 3.9.9, Surefire of Spring Boot 3.3.5, JUnit 5 | Default |
| `gradle/` | Gradle 8.10.2, JUnit 5 | `useJUnitPlatform()` |
| `jest/` | Jest 29.7, `jest-junit` 16 | `addFileAttribute: "true"` |
| `jest-defaults/` | The same | Default: the report does not say which file a test is in |
| `vitest/` | Vitest 2.1.5 | `reporters: ["default", "junit"]` |
| `vitest-unloaded/` | Vitest 2.1.9 | `--reporter=junit`. `broken.test.ts` imports a module that is not installed, so its suite does not load |
| `pytest-unloaded/` | pytest 9.2 | `--junitxml`. `test_thumbnails.py` imports a module that is not installed, so pytest stops at collection |

They were cut down so they say nothing about the machine: properties, output and stack traces were removed, and also the time of each test case. No test case, name, outcome or timestamp was edited. In the two reports of a suite that does not load, the path of the machine in the reason was replaced by `/project`.

`sources/` has the test files that ran. The Python one ends in `.txt`, so that pytest does not collect it here. One test in each suite fails and one is skipped on purpose.
