# Contributing to hypothesis-graphql

Welcome! I am happy that you are here :)

## Report bugs

Report bugs for Hypothesis-GraphQL in the [issue tracker](https://github.com/Stranger6667/hypothesis-graphql/issues).

If you are reporting a bug, please:

-   Write a simple and descriptive title to identify the problem.
-   Describe the exact steps which reproduce the problem in as many
    details as possible.
-   Describe the behavior you observed after following the steps and
    point out what exactly is the problem with that behavior.
-   Explain which behavior you expected to see instead and why.
-   Include Python / Hypothesis-GraphQL versions.

It would be awesome if you can submit a failing test that demonstrates
the problem.

## Submitting Pull Requests

1.  Fork the repository.

2.  Enable and install [pre-commit](https://pre-commit.com) to ensure style-guides and code checks are followed.

3.  Target the `master` branch.

4.  Follow [PEP-8](https://pep8.org) for naming and [ruff](https://github.com/astral-sh/ruff) for code formatting.

5.  Tests are run using `tox`:

        tox -e py39

    The test environment above is usually enough to cover most cases
    locally.

For each pull request, we aim to review it as soon as possible. If you
wait a few days without a reply, please feel free to ping the thread by
adding a new comment.

At present the core developers are:

-   Dmitry Dygalo [@Stranger6667](https://github.com/Stranger6667)

Thanks!
