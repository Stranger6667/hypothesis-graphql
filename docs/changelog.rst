Changelog
=========

`Unreleased`_ - TBD
-------------------

**Added**

- Support for custom query printers. `#21`_
- Support for custom scalars. `#22`_

**Changed**

- Do not generate fields inside inputs if they have custom scalar types. `#38`_

**Performance**

- Additional strategy cache.

`0.6.1`_ - 2022-04-26
---------------------

**Performance**

- Improve performance on recent Hypothesis versions.

`0.6.0`_ - 2022-04-25
---------------------

**Added**

- Python 3.10 support.
- Mutations support. `#51`_
- Support PEP-561. `#26`_

**Fixed**

Invalid queries:

- Fields with the same name, but different types. `#49`_
- Fields with the same name, and the same arguments that have different enum values. `#57`_

**Performance**

- Avoid using ``st.builds`` in internal strategies. It gives ~65% data generation time reduction in schemas from the test suite. `#14`_

**Changed**

- Rename ``strategies.query`` to ``strategies.queries`` and ``strategies.schema`` to ``strategies.schemas``, so they conform with the recommended naming of Hypothesis strategies.
  Old names are preserved for backward-compatibility.
- Cache parsed GraphQL schemas.

`0.5.1`_ - 2021-08-05
---------------------

**Fixed**

- Relax dependency on ``attrs``.

`0.5.0`_ - 2021-04-30
---------------------

**Added**

- Support union types. `#42`_
- Support interfaces. `#44`_

**Fixed**

- Generate only 32-bit signed integers for the ``Int`` type. `#40`_
- Always generate required fields in argument types. `#46`_

`0.4.2`_ - 2021-04-21
---------------------

**Fixed**

- Generating invalid queries for nullable enum types as arguments. `#32`_

`0.4.1`_ - 2021-04-15
---------------------

**Fixed**

- Do not generate Unicode surrogates for ``String`` types. `#30`_

`0.4.0`_ - 2021-03-27
---------------------

**Added**

- Restricting fields in the ``query`` output via the ``fields`` argument.

`0.3.3`_ - 2021-01-15
---------------------

**Added**

- Support for Python 3.9

**Changed**

- Relax requirement on ``Hypothesis``.

`0.3.2`_ - 2020-09-27
---------------------

**Changed**

- Nullable custom scalar types are handled gracefully in argument positions.
  Non-nullable types raise a ``TypeError`` in such cases.
- Shrink ``Enum`` types to their first value instead of the first value in their sorted list.


`0.3.1`_ - 2020-06-04
---------------------

**Added**

- Support for creating ``query`` strategies from ``GraphQLSchema`` instances

`0.3.0`_ - 2020-04-12
---------------------

**Added**

- Query arguments generation

**Fixed**

- Selecting fields in queries

0.2.0 - 2020-04-10
------------------

- Initial public release

.. _Unreleased: https://github.com/stranger6667/hypothesis-graphql/compare/v0.6.1...HEAD
.. _0.6.1: https://github.com/stranger6667/hypothesis-graphql/compare/v0.6.0...v0.6.1
.. _0.6.0: https://github.com/stranger6667/hypothesis-graphql/compare/v0.5.1...v0.6.0
.. _0.5.1: https://github.com/stranger6667/hypothesis-graphql/compare/v0.5.0...v0.5.1
.. _0.5.0: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.2...v0.5.0
.. _0.4.2: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.1...v0.4.2
.. _0.4.1: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.0...v0.4.1
.. _0.4.0: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.3...v0.4.0
.. _0.3.3: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.2...v0.3.3
.. _0.3.2: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.1...v0.3.2
.. _0.3.1: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.0...v0.3.1
.. _0.3.0: https://github.com/stranger6667/hypothesis-graphql/compare/v0.2.0...v0.3.0

.. _#57: https://github.com/Stranger6667/hypothesis-graphql/57
.. _#51: https://github.com/Stranger6667/hypothesis-graphql/51
.. _#49: https://github.com/Stranger6667/hypothesis-graphql/49
.. _#46: https://github.com/Stranger6667/hypothesis-graphql/46
.. _#44: https://github.com/Stranger6667/hypothesis-graphql/44
.. _#42: https://github.com/Stranger6667/hypothesis-graphql/42
.. _#40: https://github.com/Stranger6667/hypothesis-graphql/40
.. _#38: https://github.com/Stranger6667/hypothesis-graphql/38
.. _#32: https://github.com/Stranger6667/hypothesis-graphql/32
.. _#30: https://github.com/Stranger6667/hypothesis-graphql/30
.. _#26: https://github.com/Stranger6667/hypothesis-graphql/26
.. _#22: https://github.com/Stranger6667/hypothesis-graphql/22
.. _#21: https://github.com/Stranger6667/hypothesis-graphql/21
.. _#14: https://github.com/Stranger6667/hypothesis-graphql/14
