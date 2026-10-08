# ROS 2 Jazzy — интеграция

ROS/Gazebo/colcon теперь фактически запущены внутри Docker Linux ARM64.
Проверены реальные odom/scan/clock, `TwistStamped`, физическое движение и TF.
См. [Docker README](../docker/README.md) и [проверки и ограничения](../docs/validation.md).
Команды установки прямо на Ubuntu ниже отдельно не испытаны.

## Подготовка Ubuntu

В существующем клоне DID_hack, ветка night-mvp:

```sh
source /opt/ros/jazzy/setup.bash
export TURTLEBOT3_MODEL=burger
sudo apt install python3-colcon-common-extensions ros-jazzy-turtlebot3-gazebo \
  ros-jazzy-ros-gz-sim ros-jazzy-ros-gz-bridge ros-jazzy-nav2-map-server \
  ros-jazzy-nav2-lifecycle-manager ros-jazzy-tf2-ros
colcon build --base-paths ros2 --packages-select did_robot
source install/setup.bash
```

Это подготовленные команды, а не журнал успешного выполнения. ROS устанавливается
только на Ubuntu. Пакет использует существующие packages/agent, contracts,
environment через package_dir; копий ядра в ros2 нет. Сначала обычная сборка,
без --symlink-install. launch/config/maps устанавливаются в share/did_robot.

## Проверка координат до движения

```sh
ros2 launch did_robot easy.launch.py headless:=true mock_judge:=true
```

Mock включать только при отсутствии официального судьи. Если мир уже запущен,
добавить `start_world:=false`; убедиться, что существует только один источник
/cmd_vel и один комплект /did/*.

По умолчанию агент неподвижен, autostart=false, coordinates_verified=false.

```sh
ros2 topic list
ros2 topic info /cmd_vel -v
ros2 topic echo /odom --once
ros2 topic echo /scan --once
ros2 topic echo /clock --once
ros2 topic echo /did/battery --once
ros2 topic echo /did/sample_sensor --once
ros2 topic echo /did/agent/state --once
```

Проверить /tf, /imu и /joint_states от TurtleBot3. /cmd_vel должен иметь тип
geometry_msgs/msg/TwistStamped. /map должен иметь frame_id=map.

**Расхождение исходных материалов:** DOCX требует x_pose=y_pose=0 и формулы
world=(-2,-0.5)+odom. Текущий upstream launch имеет defaults x_pose=-2,
y_pose=-0.5. Тип координат /odom необходимо измерить для конкретной установленной версии. В нашем launch x_pose/y_pose вынесены в аргументы;
configs/agent.json содержит единственное явное преобразование odom_x/odom_y/
odom_yaw. На проверенном Docker ARM64 TurtleBot3 2.3.7 odom начинается около нуля,
а мировая поза (-2,-0.5), поэтому смещение (-2,-0.5,0) подтверждено измерением.
Headless launch исправляет лишний `/` в штатном TF-префиксе и публикует
map → odom из того же config_file. На другой версии снова выполнить smoke.

1. Сопоставить реальную позу/курс модели в Gazebo с /odom и TF.
2. Проверить положение столбов и базы на карте. Если odom уже мировая,
   задать odom_x=odom_y=0 в отдельном проверенном config_file.
3. Если установленный мир/версия требуют x_pose=y_pose=0 по DOCX, передать
   эти аргументы; убедиться, что робот действительно находится в (-2,-0.5).
4. Проехать небольшое расстояние через совместимый teleop и сверить смещение.
   Перед автономным запуском выключить teleop, чтобы он не публиковал /cmd_vel.
5. Только после совпадения систем координат разрешить миссию:

```sh
ros2 param set /did_agent coordinates_verified true
ros2 service call /did/agent/start std_srvs/srv/Trigger '{}'
ros2 topic echo /did/agent/state
```

Агент отказывает в старте без свежих odom/scan/clock/battery/signal и свободной
базы на карте. Неверные настройки системы координат не исправляются автоматически.

## Управление и диагностика

```sh
ros2 service call /did/agent/pause std_srvs/srv/Trigger '{}'
ros2 service call /did/agent/resume std_srvs/srv/Trigger '{}'
ros2 service call /did/agent/return std_srvs/srv/Trigger '{}'
ros2 service call /did/agent/stop std_srvs/srv/Trigger '{}'
ros2 topic echo /did/agent/journal
ros2 topic echo /did/score
ros2 topic echo /did/events
```

Команды доступны только в соответствующем состоянии. stop и pause обнуляют
скорость; return прерывает текущий путь и строит новый до базы. После зависания
/clock, устаревания лидара или пропажи odom команды обнуляются. После сброса
sim_time назад перезапустить узел и судью: старые наблюдения больше не валидны.
Повторная миссия требует сброса/перезапуска сценария; start не сбрасывает судью.

Успех: state.status=finished, collected>=1, delivered=collected, робот на базе,
/cmd_vel нулевой, finish.success=true. Если finish отклонён, delivered остаётся 0.
Поставляемый configs/agent.json задаёт goal_samples=3 (внутренний fallback
AgentConfig без файла — 1); можно изменить config_file, но возврат по энергии имеет
приоритет даже при недоборе. Среда EASY при этом всегда содержит три образца.

## Интерфейсы

| Интерфейс | Тип | Источник / назначение |
|---|---|---|
| /cmd_vel | geometry_msgs/msg/TwistStamped | agent → робот |
| /odom | nav_msgs/msg/Odometry | робот → агент и mock |
| /scan | sensor_msgs/msg/LaserScan | робот → safety |
| /clock | rosgraph_msgs/msg/Clock | время симуляции |
| /map | nav_msgs/msg/OccupancyGrid | map_server → A* |
| /did/battery | std_msgs/msg/Float32 | судья, старт 60 |
| /did/sample_sensor | std_msgs/msg/Float32 | судья, скаляр 0..1 без направления |
| /did/collect | std_srvs/srv/Trigger | агент → судья |
| /did/finish | std_srvs/srv/Trigger | агент → судья |
| /did/score | std_msgs/msg/String | JSON судьи |
| /did/events | std_msgs/msg/String | JSON событий судьи |
| /did/agent/state | std_msgs/msg/String | MissionState JSON |
| /did/agent/journal | std_msgs/msg/String | последние 50 записей журнала |
| /did/agent/knowledge | std_msgs/msg/String | публичные path/costs/planner_source |
| /did/agent/start,pause,resume,return,stop | std_srvs/srv/Trigger | управление единственным агентом |
| /did/mock/start | std_srvs/srv/Trigger | начало эпохи событий локального mock |

Mock-правила EASY: энергия 1 ед/м, внутри одной круговой зоны 2 ед/м, поворот
0.03 ед/радиан; сигнал exp(-distance/0.9)+Gaussian noise sigma=0.015; штраф за
ложный сбор 0.2. Сбор строго при расстоянии <0.30 м; finish только на базе с
положительной батареей. Эти правила не заданы организаторами и не являются
официальным скорингом. Координаты целей не публикуются. MEDIUM/HARD добавляют зоны повышенного
расхода; HARD меняет стоимость, включает опасность и временно невалидный
сигнал. Это изменения mock-энергии/датчика, а не физических материалов
или трения Gazebo; подробнее [environment](../packages/environment/README.md).

Источники: [официальный launch Jazzy](https://github.com/ROBOTIS-GIT/turtlebot3_simulations/blob/jazzy/turtlebot3_gazebo/launch/turtlebot3_world.launch.py),
[мост Burger с TwistStamped](https://github.com/ROBOTIS-GIT/turtlebot3_simulations/blob/jazzy/turtlebot3_gazebo/params/turtlebot3_burger_bridge.yaml).

После критического аудита frames проверяются строго: odom → base_footprint,
scan в base_scan. Неверный frame снимает старое наблюдение. После emergency
повторный start не снимает защёлку; устранить причину и перезапустить узел.
Unknown lidar beams блокируют движение/вращение. Подробности: [validation](../docs/validation.md).
