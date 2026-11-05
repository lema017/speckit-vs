# Real test reports

What these runners wrote when they ran the tests in `sources/`, with the Spring Boot 3.3 and TypeScript 5.6 project around them:

| Directory | Runner | Configuration |
|---|---|---|
| `surefire/` | Maven 3.9.9, Surefire of Spring Boot 3.3.5, JUnit 5 | Default |
| `gradle/` | Gradle 8.10.2, JUnit 5 | `useJUnitPlatform()` |
| `jest/` | Jest 29.7, `jest-junit` 16 | `addFileAttribute: "true"` |
| `jest-defaults/` | The same | Default: the report does not say which file a test is in |
| `vitest/` | Vitest 2.1.5 | `reporters: ["default", "junit"]` |

They were cut down so they say nothing about the machine: properties, output and stack traces were removed, and also the time of each test case. No test case, name, outcome or timestamp was edited.

`sources/` has the test files that ran. One test in each suite fails and one is skipped on purpose.
