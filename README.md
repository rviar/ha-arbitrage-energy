# Energy Arbitrage Integration для Home Assistant

Кастомная интеграция для Home Assistant, реализующая автоматизированный энергетический арбитраж с солнечными панелями и батареями.

## Возможности

- 🔋 **Умный арбитраж**: Автоматическая покупка дешевой и продажа дорогой электроэнергии
- ☀️ **Интеграция с солнечными панелями**: Оптимизация использования солнечной энергии
- 📊 **MQTT поддержка**: Получение почасовых тарифов через MQTT
- ⚡ **Управление инвертором**: Автоматическое переключение режимов работы
- 🎛️ **Гибкая настройка**: Полная конфигурация через UI Home Assistant
- 📈 **Мониторинг**: Детальные сенсоры для отслеживания эффективности

## Установка

### Через HACS (рекомендуется)

1. Откройте HACS в Home Assistant
2. Перейдите в раздел "Integrations"
3. Нажмите на три точки в верхнем правом углу
4. Выберите "Custom repositories"
5. Добавьте URL: `https://github.com/rviar/ha-energy-arbitrage`
6. Выберите категорию "Integration"
7. Нажмите "Add"
8. Найдите "Energy Arbitrage" и установите

### Ручная установка

1. Скачайте последний релиз
2. Распакуйте в папку `custom_components/energy_arbitrage/`
3. Перезагрузите Home Assistant

## Конфигурация

### Базовые требования

Убедитесь, что у вас настроены:

1. **Солнечная система** (ha-solarman):
   - `sensor.inverter_pv_power` - текущая генерация
2. **Прогноз солнечной генерации** (ha-solcast-solar):

   - `sensor.solcast_pv_forecast_forecast_today`
   - `sensor.solcast_pv_forecast_forecast_tomorrow`

3. **Батарейная система**:

   - `sensor.inverter_battery` - уровень заряда (%)
   - `sensor.inverter_battery_power` - мощность заряда/разряда

4. **Энергосистема**:

   - `sensor.inverter_load_power` - потребление дома
   - `sensor.inverter_grid_power` - импорт/экспорт в сеть

5. **Управление инвертором**:

   - `select.inverter_work_mode` - режим работы
   - `switch.inverter_battery_grid_charging` - заряд с сети

6. **MQTT тарифы** (ha_Pstryk):
   - Топик `energy/forecast/buy` - тарифы покупки
   - Топик `energy/forecast/sell` - тарифы продажи

### Настройка интеграции

1. Перейдите в **Settings** → **Devices & Services**
2. Нажмите **Add Integration**
3. Найдите **Energy Arbitrage**
4. Следуйте мастеру настройки:

#### Шаг 1: Сенсоры солнечной и энергосистемы

- Выберите ваши entity_id для всех сенсоров
- Значения по умолчанию настроены под ваши entity_id

#### Шаг 2: Управление инвертором

- Выберите select и switch для управления инвертором

#### Шаг 3: MQTT тарифы

- Укажите MQTT топики для тарифов (по умолчанию уже настроены)

#### Шаг 4: Системные параметры

- Максимальная мощность панелей: **10.6 кВт**
- Емкость батареи: **15 кВт⋅ч**
- Минимальный резерв: **20%**
- Эффективность батареи: **90%**
- И другие параметры

## Создаваемые entity

### Сенсоры

- `sensor.energy_arbitrage_next_action` - Следующее действие системы
- `sensor.energy_arbitrage_target_power` - Целевая мощность заряда/разряда
- `sensor.energy_arbitrage_profit_forecast` - Прогноз прибыли (EUR)
- `sensor.energy_arbitrage_battery_target` - Целевой уровень заряда батареи
- `sensor.energy_arbitrage_roi` - Ожидаемая рентабельность (%)
- `sensor.energy_arbitrage_status` - Статус системы

### Переключатели

- `switch.energy_arbitrage_enabled` - Включение/выключение арбитража
- `switch.energy_arbitrage_emergency_mode` - Аварийный режим

### Селекторы

- `select.energy_arbitrage_strategy` - Выбор стратегии арбитража

## Сервисы

### `energy_arbitrage.recalculate`

Принудительный пересчет арбитражных возможностей.

### `energy_arbitrage.set_battery_reserve`

```yaml
service: energy_arbitrage.set_battery_reserve
data:
  reserve_percent: 25
```

### `energy_arbitrage.manual_override`

```yaml
service: energy_arbitrage.manual_override
data:
  hours: 2
```

### `energy_arbitrage.clear_manual_override`

Отмена ручного управления.

### `energy_arbitrage.force_work_mode`

```yaml
service: energy_arbitrage.force_work_mode
data:
  work_mode: 'Export First'
  duration_minutes: 30
```

### `energy_arbitrage.force_grid_charging`

```yaml
service: energy_arbitrage.force_grid_charging
data:
  enable: true
  duration_minutes: 60
```

## Логика работы

### Алгоритм принятия решений

Система использует **приоритетную иерархию** для принятия оптимальных решений по управлению энергией:

```
Проверки безопасности → Поиск арбитража → Управление солнечной энергией → Покрытие нагрузки → Удержание
```

#### Предварительные проверки

1. **Лимит дневных циклов батареи**

   - Проверка: `today_cycles ≥ max_daily_cycles` (по умолчанию 2.0)
   - Если превышен → `HOLD` (остановка операций)

2. **Минимальный уровень для арбитража**
   - Проверка: `battery_level ≥ 40%`
   - Если ниже → `HOLD` (защита батареи)

#### 🔴 ПРИОРИТЕТ 1: Продажа арбитража (`sell_arbitrage`)

**Условия:**

- ✅ ROI ≥ 5% (минимальная маржа)
- ✅ Цена продажи максимальная в 24ч периоде
- ✅ Батарея выше резерва + 10% буфер
- ✅ Доступна энергия для разрядки

**Действие:** Разрядка батареи для продажи энергии по высоким тарифам

#### 🟢 ПРИОРИТЕТ 2: Покупка арбитража (`charge_arbitrage`)

**Условия:**

- ✅ ROI ≥ 5% для будущей продажи
- ✅ Цена покупки минимальная в 24ч периоде
- ✅ Батарея ниже 95%

**Действие:** Зарядка батареи дешевой энергией для последующей продажи

**🔄 Остальные операции выполняет инвертер автоматически:**

- **Зарядка от солнца:** Инвертер сам управляет зарядкой батареи от PV
- **Экспорт излишков:** Инвертер сам экспортирует излишки в сеть
- **Покрытие нагрузки:** Инвертер сам разряжает батарею для покрытия потребления

_Система арбитража вмешивается только при наличии выгодных торговых возможностей_

#### ⚪ По умолчанию: Удержание (`hold`)

Если ни одно условие не выполнено, система остается в режиме ожидания.

### Ключевые параметры

| Параметр                 | Значение | Назначение                        |
| ------------------------ | -------- | --------------------------------- |
| **Min Arbitrage Margin** | 15%      | Минимальная прибыль для арбитража |
| **Max Daily Cycles**     | 2.0      | Защита батареи от износа          |
| **Min Arbitrage Depth**  | 40%      | Минимальный уровень для арбитража |

### Анализ арбитражных возможностей

1. **Получение ценовых данных** через MQTT топики
2. **Расчет ROI** с учетом эффективности батареи (90%)
3. **Определение временных окон** для покупки/продажи
4. **Сортировка возможностей** по убыванию прибыльности

### Режимы инвертора

- **Export First**: Приоритет экспорта в сеть (для продажи)
- **Zero Export To Load**: Приоритет самопотребления (для заряда/хранения)

### Защитные механизмы

- **Минимальный резерв батареи**: 20% (настраивается)
- **Cooldown между действиями**: 5 минут
- **Аварийный режим**: Сохранение заряда батареи
- **Ручное управление**: Временное отключение автоматики

## Мониторинг в Home Assistant

### Пример карточки дашборда

```yaml
type: entities
title: Energy Arbitrage
entities:
  - sensor.energy_arbitrage_status
  - sensor.energy_arbitrage_next_action
  - sensor.energy_arbitrage_target_power
  - sensor.energy_arbitrage_profit_forecast
  - sensor.energy_arbitrage_roi
  - switch.energy_arbitrage_enabled
  - switch.energy_arbitrage_emergency_mode
  - select.energy_arbitrage_strategy
```

### Автоматизация

```yaml
automation:
  - alias: 'Energy Arbitrage Notification'
    trigger:
      - platform: state
        entity_id: sensor.energy_arbitrage_roi
        above: 10
    action:
      - service: notify.telegram
        data:
          message: "Выгодная арбитражная возможность: {{ states('sensor.energy_arbitrage_roi') }}% ROI!"
```

## Troubleshooting

### Проблемы с MQTT

- Убедитесь, что MQTT брокер доступен
- Проверьте топики `energy/forecast/buy` и `energy/forecast/sell`
- Данные должны быть в формате JSON массива

### Проблемы с управлением инвертором

- Проверьте доступность entity_id инвертора
- Убедитесь, что select.inverter_work_mode поддерживает нужные режимы
- Проверьте права доступа к switch.inverter_battery_grid_charging

### Отсутствие арбитражных решений

- Проверьте настройку минимальной маржи (по умолчанию 5%)
- Убедитесь в корректности прогноза тарифов
- Проверьте уровень заряда батареи и минимальный резерв

## Поддержка

- **Issues**: [GitHub Issues](https://github.com/rviar/ha-energy-arbitrage/issues)
- **Документация**: [Wiki](https://github.com/rviar/ha-energy-arbitrage/wiki)
- **Community**: [Home Assistant Community Forum](https://community.home-assistant.io/)

## Лицензия

MIT License - см. [LICENSE](LICENSE) файл.

## Changelog

### v1.0.0

- Первый релиз
- Базовый функционал арбитража
- MQTT интеграция для тарифов
- UI конфигурация
- Полный набор сенсоров и сервисов# ha-arbitrage-energy
