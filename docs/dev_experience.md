# Developer Experience Design

The PRD is product focused and do not typically contain any design related to the developer experience.

This file designs the developer experience so that it can be added to the TDD. This file tries to be
project agnostic so that the developer experience can be optimized to specific projects needs. For example,
this file will recommend linting as part of the CI tooling. If the project is Python focused, then the TDD
must design to have a Python linter run as part of the project's CI toolchain.

## Requirements

1. All development must be associated with a Github Issue
2. All development must be in a Git feature branch
3. All development must follow the Github Pull Request workflow
4. Lightweight workflow requirements
   1. The lightweight workflow must run before code is commited to Git (Git pre-commit)
   2. The lightweight workflow must run as a Github pull-request check
      1. After completing as a Github pull-request check, the key results of the lightweight workflow must be accessible from the pull request
   3. The lightweight workflow must format all code to a well-established style guide when possible
   4. The lightweight workflow must run linters for all code when possible
   5. The lightweight workflow must run unit tests
5. Issue-level workflow requirements
   1. The issue-level workflow must run as a Github pull-request check
      1. After completing as a Github pull-request check, the key results of the lightweight workflow must be accessible from the pull request
   2. The issue-level workflow must run unit tests in multiple variations of the environment. The variations must be relevant to users (e.g. Python version variations)
6. All developer experience work should be completed before development of the product itself
