## [1.5.1](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.5.0...v1.5.1) (2026-10-25)


### Bug Fixes

* **deps:** patch semantic-release tooling dependencies ([3e2a27d](https://github.com/aleksanderbl29/dmi-homeassistant/commit/3e2a27d6037adb4ec383562554f2bb90e6b30bc3))
* **manifest:** use Home Assistant provided aiohttp ([4bd2e06](https://github.com/aleksanderbl29/dmi-homeassistant/commit/4bd2e06f7c50772f96e8b6e70bf636393680dcc4))

# [1.5.0](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.4.2...v1.5.0) (2026-08-02)


### Features

* **sea:** support observation sources for prediction-only stations ([e28f68f](https://github.com/aleksanderbl29/dmi-homeassistant/commit/e28f68fe4f607e0b80a1ad66a303697a09a3a7aa))

## [1.4.2](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.4.1...v1.4.2) (2026-08-01)


### Bug Fixes

* **sea:** include prediction-only stations ([05ad675](https://github.com/aleksanderbl29/dmi-homeassistant/commit/05ad6752bbfd206e7028bf02cf24e4086fadb9e6))

## [1.4.1](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.4.0...v1.4.1) (2026-07-27)


### Bug Fixes

* **coordinator:** share DMI rate-limit state ([f8d7c7c](https://github.com/aleksanderbl29/dmi-homeassistant/commit/f8d7c7ca86f9b2c92329b434a0df5708b835ba29))

# [1.4.0](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.3.0...v1.4.0) (2026-07-26)


### Bug Fixes

* **api:** reduce DKSS forecast payloads ([2f021eb](https://github.com/aleksanderbl29/dmi-homeassistant/commit/2f021eb3e3884c95d477a31ee513824a57cce9fb))
* **coordinator:** isolate forecast API failures ([1c4571d](https://github.com/aleksanderbl29/dmi-homeassistant/commit/1c4571d3a1560a5fd8d83f8c2ee88f9af842c871))
* **coordinator:** preserve setup during rate limits ([db56871](https://github.com/aleksanderbl29/dmi-homeassistant/commit/db5687140f65ad5122acb6bddf5ea32470f711ab))
* **sea:** reduce forecast API requests ([9f3d055](https://github.com/aleksanderbl29/dmi-homeassistant/commit/9f3d0550e91f4c2622e9f0d7a4e26005b7a9112f))


### Features

* **api:** add astronomical tide forecasts ([4fb27f1](https://github.com/aleksanderbl29/dmi-homeassistant/commit/4fb27f134f164a2dace3fa269ccc9b0f5250affa))
* **api:** add coordinate-based DKSS forecasts ([766b62a](https://github.com/aleksanderbl29/dmi-homeassistant/commit/766b62a66fda382773b790df7865d1904eaa3f7f))
* **api:** add ocean observation support ([8b7bc76](https://github.com/aleksanderbl29/dmi-homeassistant/commit/8b7bc765792998ecbc5776d55da79376ce062280))
* **config:** confirm automatic tide station match ([951cb92](https://github.com/aleksanderbl29/dmi-homeassistant/commit/951cb92109507b7396a5de03728577d1c814852a))
* **sea:** add tide-gauge sensor setup ([f1a3733](https://github.com/aleksanderbl29/dmi-homeassistant/commit/f1a37334b215fee3aacb2ff82aaeff874e7bf437))
* **sea:** configure tide prediction stations ([744e11e](https://github.com/aleksanderbl29/dmi-homeassistant/commit/744e11e4bdf11cec6cc9b209721f3609500a2013))
* **sensor:** expose astronomical tide predictions ([5829c94](https://github.com/aleksanderbl29/dmi-homeassistant/commit/5829c94cd2d7ebd10e2a95fa73152b3444e4801c))
* **sensor:** expose DKSS sea-level forecasts ([7581cee](https://github.com/aleksanderbl29/dmi-homeassistant/commit/7581cee5b2da784f91ecb292520a2e83abe4b586))

# [1.3.0](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.2.0...v1.3.0) (2026-07-06)


### Bug Fixes

* **api:** paginate stations and sort observations ([0d3fe48](https://github.com/aleksanderbl29/dmi-homeassistant/commit/0d3fe48b75604a17677af55db63cfa625d10f871))
* **coordinator:** stagger backup observation requests ([c5aba40](https://github.com/aleksanderbl29/dmi-homeassistant/commit/c5aba4049120ae99a9ea45e4d185ef38cc28c4c8))


### Features

* **config-flow:** finish when backups add all data ([c0f824b](https://github.com/aleksanderbl29/dmi-homeassistant/commit/c0f824beee93d46cb7168b79c9d4f00fd9ff8738))
* **config-flow:** let users choose backup parameters ([4ece974](https://github.com/aleksanderbl29/dmi-homeassistant/commit/4ece974fa1f7b17498953ac3c2f376c581f7bd3f))
* **sensor:** add dynamic observation sensors ([294548b](https://github.com/aleksanderbl29/dmi-homeassistant/commit/294548b7b283e1624ab3d64d58bb2316a436c1da))

# [1.2.0](https://github.com/aleksanderbl29/dmi-homeassistant/compare/v1.1.1...v1.2.0) (2026-07-04)


### Bug Fixes

* **config-flow:** prevent duplicate backup parameters ([e7485d9](https://github.com/aleksanderbl29/dmi-homeassistant/commit/e7485d978bcb4b380b16f36ceb27e13c8cd073ff))
* **config:** default backup station suffix on ([d7fd2e4](https://github.com/aleksanderbl29/dmi-homeassistant/commit/d7fd2e43ec26c1b696a324a1d73d08d1882a8c94))
* **coordinator:** tolerate failed advanced backups ([fc0e542](https://github.com/aleksanderbl29/dmi-homeassistant/commit/fc0e54260bc30ae587e417af1c067d6f3792b496))
* **sensor:** separate backup station suffix ([5fc6cb1](https://github.com/aleksanderbl29/dmi-homeassistant/commit/5fc6cb19d833ec0f359a55a4f5e2835af7237eec))


### Features

* **dmi:** simplify advanced backup sensor setup ([253f0b4](https://github.com/aleksanderbl29/dmi-homeassistant/commit/253f0b4a3e16985893b0f69aa3a9379feb459764))

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
