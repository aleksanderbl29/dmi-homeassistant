## [1.1.1](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.1.0...v1.1.1) (2026-07-04)


### Bug Fixes

* **forecast:** normalize precipitation and cloud cover ([c7a10f2](https://github.com/aleksanderbl29/dmi-homeassistant/commit/c7a10f210aa345ae38a8342ca09247d5ad4c4f1b))

# [1.1.0](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.0.1...v1.1.0) (2026-07-02)


### Bug Fixes

* **caching:** keep cached data on refresh failures ([#12](https://github.com/aleksanderbl29/dmi-homeassistant/issues/12)) ([7d6c18f](https://github.com/aleksanderbl29/dmi-homeassistant/commit/7d6c18f01ffeff645b07161af55af574150d73f6))
* **dmi:** preserve cached data on upstream failures ([bab5d78](https://github.com/aleksanderbl29/dmi-homeassistant/commit/bab5d781af991607cfde8c55cd5961c9898bf230))
* retain cached DMI data on refresh failures ([8a9b60b](https://github.com/aleksanderbl29/dmi-homeassistant/commit/8a9b60b30df9fab8c8f6af90a23f386b320d9fbb))


### Features

* **dmi:** add diagnostic last successful update sensor ([9d772b3](https://github.com/aleksanderbl29/dmi-homeassistant/commit/9d772b398676468f17fd3c04f0facece5647cf6e))

## [1.0.1](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.0.0...v1.0.1) (2026-07-01)


### Bug Fixes

* **listing:** consolidate duplicate DMI station listings ([#7](https://github.com/aleksanderbl29/dmi-homeassistant/issues/7)) ([597a2b2](https://github.com/aleksanderbl29/dmi-homeassistant/commit/597a2b289129ed1c1b0ad56786ecdfed8bd36ae0))

# 1.0.0 (2026-07-01)


### Bug Fixes

* **api:** enforce no-auth DMI open-data policy ([#4](https://github.com/aleksanderbl29/dmi-homeassistant/issues/4)) ([3f8a4b4](https://github.com/aleksanderbl29/dmi-homeassistant/commit/3f8a4b4e339860383201b1b4185fbb17dd858e90))
* Correct API URL structure and observation fetching ([eef2feb](https://github.com/aleksanderbl29/dmi-homeassistant/commit/eef2febe1bf52122acf9a5e597093a4dbe47124e))
* correct forecast parameters, rate-limit handling, and CI validation ([b645e97](https://github.com/aleksanderbl29/dmi-homeassistant/commit/b645e97827737004ec52a8dc6309c4276cfb132b))
* Improve error handling and prevent NoneType errors ([ee734e8](https://github.com/aleksanderbl29/dmi-homeassistant/commit/ee734e8012560844466d2aa7bbc96b43a5a7840f))
* resolve CI failures for hassfest, tests, and Python version ([5e80f27](https://github.com/aleksanderbl29/dmi-homeassistant/commit/5e80f270d519a7f7ee7f9a213e6b91f408338d2d))


### Features

* Add comprehensive pytest testing suite with GitHub Actions CI ([98387ce](https://github.com/aleksanderbl29/dmi-homeassistant/commit/98387cea6f16cc1d512a7042bc92caf9df18026f))
* Improve HA compliance and logging; add attribution and unit fixes ([19eda52](https://github.com/aleksanderbl29/dmi-homeassistant/commit/19eda529f24bc8ab0ef282b45f0845175107bb61))
* Initial implementation of DMI Weather integration ([8d031f2](https://github.com/aleksanderbl29/dmi-homeassistant/commit/8d031f2e89236b055bdd6670c48a0ffcb7066029))

# Changelog

All notable changes to this project will be documented in this file.
