.. _changelog:

Changelog
=========

`Unreleased`_
-------------

Changed
~~~~~~~

- Relax requirement on ``Hypothesis``.

`0.3.2`_ - 2020-09-27
---------------------

Changed
~~~~~~~

- Nullable custom scalar types are handled gracefully in argument positions.
  Non-nullable types raise a ``TypeError`` in such cases.
- Shrink ``Enum`` types to their first value instead of the first value in their sorted list.


`0.3.1`_ - 2020-06-04
---------------------

Added
~~~~~

- Support for creating ``query`` strategies from ``GraphQLSchema`` instances

`0.3.0`_ - 2020-04-12
---------------------

Added
~~~~~

- Query arguments generation

Fixed
~~~~~

- Selecting fields in queries

0.2.0 - 2020-04-10
------------------

- Initial public release

.. _Unreleased: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.2...HEAD
.. _0.3.2: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.1...v0.3.2
.. _0.3.1: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.0...v0.3.1
.. _0.3.0: https://github.com/stranger6667/hypothesis-graphql/compare/v0.2.0...v0.3.0

.. _#2: https://github.com/stranger6667/hypothesis-graphql/issues/2
