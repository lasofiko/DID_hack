# Environment — Искандер

Написать генератор easy/medium/hard и судью либо использовать официального.
Судья хранит скрытые цели и расписание, считает энергию, сбор и завершение.
Публичные ROS-интерфейсы: /did/battery, /did/sample_sensor (Float32),
/did/collect, /did/finish (Trigger), /did/score, /did/events (String JSON).
Закон расхода и штрафы сначала уточнить у организаторов; скрытые данные не публиковать.
TaskServices — клиент этих сервисов в ROS-адаптере. Подробности: ../../docs/team.md.
