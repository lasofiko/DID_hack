# Configs

agent.json — единые параметры контроллера, безопасности, батареи, поиска и базы.
Включает явное преобразование odom → map. На проверенном Docker ARM64
TurtleBot3 2.3.7 odom начинается около (0,0), база/world=(-2,-0.5),
поэтому смещение (-2,-0.5,0) подтверждено на старте. На другой версии
повторить проверку TF и физической позы; фиксированный offset не исправляет drift.
Параметры navigation clearance=0.35 м и mock clearance=0.20 м независимы.
goal_samples=3 в поставляемом config; возврат по энергии имеет приоритет.

maps/ — официальный снимок карты TurtleBot3 Jazzy, лицензия и SHA-256 в SOURCE.md.
Карта доступна как ROS map_server YAML/PGM и для dependency-free тестов A*.
Диагностика: [ROS](../ros2/README.md), [validation](../docs/validation.md).
