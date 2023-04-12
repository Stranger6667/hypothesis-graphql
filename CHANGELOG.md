# Changelog

## [Unreleased] - TBD

## [0.10.0] - 2023-04-12

### Changed

- **Build**: Switch the build backend to [Hatch](https://hatch.pypa.io/>).

### Removed

- Python 3.6 support.
- Dependency on `attrs`.

## [0.9.2] - 2022-11-07

### Added

- Support for Python 3.11.

## [0.9.1] - 2022-09-02

- Use `poetry-core` for building the package.

## [0.9.0] - 2022-04-29

### Added

- The `from_schema` function which takes a GraphQL schema and returns a Hypothesis strategy for defined queries and mutations.

### Changed

- Use Hypothesis' `InvalidArgument` exception when an invalid input is passed to the generator functions.

### Removed

- `hypothesis_graphql.schemas` as it is not complete and not tested well.

## [0.8.2] - 2022-04-29

### Fixed

- Internal error on some invalid schemas.

## [0.8.1] - 2022-04-27

### Added

- Expose `validate_scalar_strategy` in the public API.

## [0.8.0] - 2022-04-27

### Added

- Support for using default values of arguments and input fields. #71

### Fixed

- Duplicated inline fragments that may miss aliases. #69
- Queries missing required fields in their inputs when these fields are custom scalars.

## [0.7.1] - 2022-04-27

### Added

- `hypothesis_graphql.nodes` module to simplify working with custom scalars.

## [0.7.0] - 2022-04-26

### Added

- Support for custom query printers. #21
- Support for custom scalars. #22

### Changed

- Do not generate fields inside inputs if they have custom scalar types. #38
- Generate `null` for nullable custom scalars in the argument position. #35

### Performance

- Additional strategy cache.

## [0.6.1] - 2022-04-26

### Performance

- Improve performance on recent Hypothesis versions.

## [0.6.0] - 2022-04-25

### Added

- Python 3.10 support.
- Mutations support. #51
- Support PEP-561. #26

### Fixed

Invalid queries:

- Fields with the same name, but different types. #49
- Fields with the same name, and the same arguments that have different enum values. #57

### Performance

- Avoid using `st.builds` in internal strategies. It gives ~65% data generation time reduction in schemas from the test suite. #14

### Changed

- Rename `strategies.query` to `strategies.queries` and `strategies.schema` to `strategies.schemas`, so they conform with the recommended naming of Hypothesis strategies.
  Old names are preserved for backward-compatibility.
- Cache parsed GraphQL schemas.

## [0.5.1] - 2021-08-05

### Fixed

- Relax dependency on `attrs`.

## [0.5.0] - 2021-04-30

### Added

- Support union types. #42
- Support interfaces. #44

### Fixed

- Generate only 32-bit signed integers for the `Int` type. #40
- Always generate required fields in argument types. #46

## [0.4.2] - 2021-04-21

### Fixed

- Generating invalid queries for nullable enum types as arguments. #32

## [0.4.1] - 2021-04-15

### Fixed

- Do not generate Unicode surrogates for `String` types. #30

## [0.4.0] - 2021-03-27

### Added

- Restricting fields in the `query` output via the `fields` argument.

## [0.3.3] - 2021-01-15

### Added

- Support for Python 3.9

### Changed

- Relax requirement on `Hypothesis`.

## [0.3.2] - 2020-09-27

### Changed

- Nullable custom scalar types are handled gracefully in argument positions.
  Non-nullable types raise a `TypeError` in such cases.
- Shrink `Enum` types to their first value instead of the first value in their sorted list.

## [0.3.1] - 2020-06-04

### Added

- Support for creating `query` strategies from `GraphQLSchema` instances

## [0.3.0] - 2020-04-12

### Added

- Query arguments generation

### Fixed

- Selecting fields in queries

## [0.2.0] - 2020-04-10

- Initial public release

[Unreleased]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.9.2...v0.10.0
[0.9.2]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.8.2...v0.9.0
[0.8.2]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/stranger6667/hypothesis-graphql/compare/v0.2.0...v0.3.0

[#71]: https://github.com/Stranger6667/hypothesis-graphql/71
[#69]: https://github.com/Stranger6667/hypothesis-graphql/69
[#57]: https://github.com/Stranger6667/hypothesis-graphql/57
[#51]: https://github.com/Stranger6667/hypothesis-graphql/51
[#49]: https://github.com/Stranger6667/hypothesis-graphql/49
[#46]: https://github.com/Stranger6667/hypothesis-graphql/46
[#44]: https://github.com/Stranger6667/hypothesis-graphql/44
[#42]: https://github.com/Stranger6667/hypothesis-graphql/42
[#40]: https://github.com/Stranger6667/hypothesis-graphql/40
[#38]: https://github.com/Stranger6667/hypothesis-graphql/38
[#35]: https://github.com/Stranger6667/hypothesis-graphql/35
[#32]: https://github.com/Stranger6667/hypothesis-graphql/32
[#30]: https://github.com/Stranger6667/hypothesis-graphql/30
[#26]: https://github.com/Stranger6667/hypothesis-graphql/26
[#22]: https://github.com/Stranger6667/hypothesis-graphql/22
[#21]: https://github.com/Stranger6667/hypothesis-graphql/21
[#14]: https://github.com/Stranger6667/hypothesis-graphql/14
