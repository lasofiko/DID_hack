# Эксперименты

JSON, логи и снимки сохраняются локально в runs, исключённом из Git и Docker
build context. Compose монтирует runs/docker как /workspace/output.
Приватный журнал судьи остаётся там и не обслуживается API.

scripts/check_scenarios.py и scripts/audit_seeds.py пишут в runs; для остальных
проб задавайте output в этом каталоге. Не смешивайте unit/кинематику/Gazebo.
Сравнивайте baseline/adaptive на одинаковых scenario/seed/config, измеряйте
доставку, батарею, отказы, траекторию и качество модели. Безопасный отказ HARD
не засчитывается доставкой; улучшение требует парных измерений.

Критерии: [validation](../docs/validation.md).
Контракт научной модели: [EnergyModel](../docs/ENERGY_INTEGRATION.md).
