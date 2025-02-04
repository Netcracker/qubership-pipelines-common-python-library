# Changelog

## [0.1.0] - 2025-02-04
### Changes
- Gitlab integration is moved from GitClient into a separate GitlabClient
- GitlabClient usability improved based on feedback 

## [0.0.8] - 2025-01-31
### Changes
- Added implicit context creation for invoking ExecutionCommands from other Commands without having to explicitly create context/params structure
- Next version is going to contain breaking compatibility changes - Gitlab-related functions will be moved out of GitClient into a separate client

## [0.0.1] - 2024-12-09
### Changes
- Initial version, implemented Jenkins & Git operations