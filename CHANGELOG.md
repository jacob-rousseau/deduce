# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2.0.1 (2022-12-09)

### Changed
- updated dependencies

## 2.0.0 (2022-12-05)

### Changed
- major refactor that touches pretty much every line of code
- use `docdeid` package for logic
- speedups: now 973% faster
- use lookup sets instead of lookup lists
- refactor tokenizer
- refactor annotators into separate classes, using structured annotations
- guidelines for contributing

### Added
- introduced new interface for deidentification, using `Deduce()` class
- a separate documentation page, with tutorial and migration guide
- support for python 3.10 and 3.11


### Removed
- the `annotate_text` and `deidentify_annotations` functions
- all in-text annotation (under the hood) and associated functions
- support for given names. given names can be added as another first name in the `Person` class. 
- support for python 3.7 and 3.8

### Fixed
- `<` and `>` are no longer replaced by `(` and `)` respectively
- deduce does not strip text (whitespaces, tabs at beginning/end of text) anymore

## 1.0.8 (2021-11-29)

### Fixed
- various modifications related to adding or subtracting spaces in annotated texts
- remove the lowercasing of institutions' names
- therefore, all structured annotations have texts matching the original text in the same span

### Added
- warn if there are any structured annotations whose annotated text does not match the original text in the span denoted by the structured annotation

## 1.0.7 (2021-11-03)

### Changed
- Internal code formatting improvements

### Added
- Contributing guidelines

## 1.0.6 (2021-10-06)

### Fixed
- Bug with multiple 4-digit mg dosages in one text

## 1.0.5 (2021-10-05)

### Fixed
- Minor bug where tag flattening had no effect

## 1.0.4 (2021-10-05)

### Added
- Changelog
- Additional unit tests for whitespace/punctuation

### Fixed
- Various whitespace/punctuation bugs
- Bug with nested tags not related to person names
- Bug with adjacent tags not being merged

## 1.0.3 (2021-07-07)

### Added
- Structured annotations
- Some unit tests

### Fixed
- Error with outdated unicode package
- Bug with context

## 1.0.2 
Release to PyPI

## 1.0.1 
Small bugfix for None as input

## 1.0.0 
Initial version
