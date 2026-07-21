# CHANGELOG

<!-- version list -->

## v2.2.0 (2026-07-21)

### Features

- Add SMART disk monitoring with sudo setup
  ([#396](https://github.com/worgarside/wg-scripts/pull/396),
  [`dfc9442`](https://github.com/worgarside/wg-scripts/commit/dfc9442fedd97d9997b0b9e9654676065e33736e))


## v2.1.4 (2026-07-21)

### Continuous Integration

- Update PATH for seamless CI deploy
  ([`cd44c4f`](https://github.com/worgarside/wg-scripts/commit/cd44c4faa07b065629145727a4b0d2d68d1cb93e))


## v2.1.3 (2026-07-20)

### Continuous Integration

- Improve deploy workflow with user handling
  ([`2f35272`](https://github.com/worgarside/wg-scripts/commit/2f3527282a680668fe796d78d4a8b3a926e18c05))


## v2.1.2 (2026-07-20)

### Continuous Integration

- Enhance deploy workflow with Tailscale tag support
  ([`9b69877`](https://github.com/worgarside/wg-scripts/commit/9b698774f8237b6ce3d25430352f9a6bc5803e46))


## v2.1.1 (2026-07-20)

### Continuous Integration

- Update OAuth ID source from secrets to vars
  ([`28aff06`](https://github.com/worgarside/wg-scripts/commit/28aff06247ed42231d9e8fa432e8fbeb024ccc29))


## v2.1.0 (2026-07-20)

### Continuous Integration

- Switch to deploy key for secure releases
  ([`1e7bde6`](https://github.com/worgarside/wg-scripts/commit/1e7bde681769b3d3fb910babbad4511c7ab9749c))

- Update semantic release committer details
  ([`8d592c7`](https://github.com/worgarside/wg-scripts/commit/8d592c7b4c1ed8ffacb4fae92544a0e938f05331))

- Update ssh command for runner compatibility
  ([`ca00f44`](https://github.com/worgarside/wg-scripts/commit/ca00f4449baecfc0d12fad03fadd570df66bf078))

### Features

- Add Pi 5 pwmfan RPM and PWM monitoring ([#388](https://github.com/worgarside/wg-scripts/pull/388),
  [`01c5b8b`](https://github.com/worgarside/wg-scripts/commit/01c5b8b8be212361cecc6a59a2adf979775dd30b))

- Automate deployments to target devices ([#389](https://github.com/worgarside/wg-scripts/pull/389),
  [`4ca24f0`](https://github.com/worgarside/wg-scripts/commit/4ca24f0a271b2ac0f4c327b5c87e74d9c9de78a5))

- Simplify and automate Pi setup
  ([`f1e55be`](https://github.com/worgarside/wg-scripts/commit/f1e55beda388b6594180381495622e3a2addd229))


## v2.0.2 (2026-07-19)

### Bug Fixes

- Just update
  ([`9bf4400`](https://github.com/worgarside/wg-scripts/commit/9bf4400ce82bfb45ba78036cc9085a05da129608))

### Continuous Integration

- Update release invoke to be multi-option
  ([`1213d7d`](https://github.com/worgarside/wg-scripts/commit/1213d7db4ce0c855b7bb6ed27b6d0c9f04877442))


## v2.0.1 (2026-07-19)

### Refactoring

- Round system load averages to 2 decimals
  ([#387](https://github.com/worgarside/wg-scripts/pull/387),
  [`db9935c`](https://github.com/worgarside/wg-scripts/commit/db9935c6c5d5b1db0d0057917861e8f6b6ff32fd))


## v2.0.0 (2026-07-19)

### Continuous Integration

- Remove extra prek call
  ([`3eb09f2`](https://github.com/worgarside/wg-scripts/commit/3eb09f22c500e67fc6ee5ef226a4faf394f65ca1))

### Features

- Add configurable disk usage reporting ([#383](https://github.com/worgarside/wg-scripts/pull/383),
  [`a69d958`](https://github.com/worgarside/wg-scripts/commit/a69d95881b7f8db477625686cd4b806646e0e5c9))

- Add templates for service units setup ([#386](https://github.com/worgarside/wg-scripts/pull/386),
  [`146efc8`](https://github.com/worgarside/wg-scripts/commit/146efc8c20a3438a05014498ead32068d9329aff))

- Add wg_scripts_version to pi_stats ([#385](https://github.com/worgarside/wg-scripts/pull/385),
  [`495a333`](https://github.com/worgarside/wg-scripts/commit/495a3339a2dc8227034701261950dd8ee6674a6f))

- Integrate MQTT discovery in pi_stats ([#384](https://github.com/worgarside/wg-scripts/pull/384),
  [`6b388b1`](https://github.com/worgarside/wg-scripts/commit/6b388b15b09fd2960b015a14aace33c03e557fd0))

### Refactoring

- Update project config and workflows ([#382](https://github.com/worgarside/wg-scripts/pull/382),
  [`29bffa4`](https://github.com/worgarside/wg-scripts/commit/29bffa4f84c83fd29e8354efa92c941c1a188d66))
