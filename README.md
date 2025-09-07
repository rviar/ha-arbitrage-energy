# Energy Arbitrage Integration для Home Assistant

Кастомная интеграция для Home Assistant, реализующая **предиктивный энергетический арбитраж** с солнечными панелями и батареями.

## ✨ Возможности

- 🧠 **Предиктивная система**: Планирование на 24-48 часов вперед с учетом прогнозов PV и потребления
- 🎯 **Стратегическое планирование**: Долгосрочные стратегии с оптимизацией последовательности операций
- ⏰ **Временные окна**: Точный анализ ценовых периодов для максимальной эффективности
- 🔋 **Умный арбитраж**: Автоматическая покупка дешевой и продажа дорогой электроэнергии
- ☀️ **Интеграция Solcast**: Использование прогнозов PV для точного планирования
- 📊 **MQTT поддержка**: Получение почасовых тарифов через MQTT
- ⚡ **Управление инвертором**: Автоматическое переключение режимов работы
- 🎛️ **Гибкая настройка**: Полная конфигурация через UI Home Assistant
- 📈 **Расширенный мониторинг**: Детальные сенсоры для отслеживания стратегий и планов

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

5. **Управление инвертором** (настраивается при установке):

   - `select.inverter_work_mode` - режим работы
   - `switch.inverter_battery_grid_charging` - заряд с сети
   - `select.inverter_time_of_use` - управление Time of Use (по умолчанию)
   - `switch.inverter_export_surplus` - экспорт излишков (по умолчанию)

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
- Настройте entity_id для Time of Use и Export Surplus (опционально)
- По умолчанию используются стандартные entity_id

#### Шаг 3: MQTT тарифы

- Укажите MQTT топики для тарифов (по умолчанию уже настроены)

#### Шаг 4: Системные параметры

- Максимальная мощность панелей: **10.6 кВт**
- Емкость батареи: **15 кВт⋅ч**
- Максимальная мощность батареи: **5 кВт**
- Минимальный резерв: **20%**
- **Минимальная глубина арбитража: 40%** (новый параметр)
- Эффективность батареи: **90%**
- И другие параметры

## Создаваемые entity

### Основные сенсоры

- `sensor.energy_arbitrage_next_action` - Следующее действие системы
- `sensor.energy_arbitrage_target_power` - Целевая мощность заряда/разряда
- `sensor.energy_arbitrage_profit_forecast` - Прогноз прибыли (EUR)
- `sensor.energy_arbitrage_battery_target` - Целевой уровень заряда батареи
- `sensor.energy_arbitrage_roi` - Ожидаемая рентабельность (%)
- `sensor.energy_arbitrage_status` - Статус системы

### 🧠 Предиктивные сенсоры

- `sensor.energy_arbitrage_energy_forecast` - Прогноз энергетического баланса
- `sensor.energy_arbitrage_price_windows` - Анализ ценовых окон
- `sensor.energy_arbitrage_strategic_plan` - Стратегический план операций

### 📊 Мониторинг и аналитика

- `sensor.energy_arbitrage_next_buy_window` - Следующее окно для покупки
- `sensor.energy_arbitrage_next_sell_window` - Следующее окно для продажи
- `sensor.energy_arbitrage_today_profit` - Прибыль за сегодня
- `sensor.energy_arbitrage_monthly_profit` - Прибыль за месяц
- `sensor.energy_arbitrage_current_buy_price` - Текущая цена покупки
- `sensor.energy_arbitrage_current_sell_price` - Текущая цена продажи
- И многие другие...

### Переключатели

- `switch.energy_arbitrage_enabled` - Включение/выключение арбитража
- `switch.energy_arbitrage_emergency_mode` - Аварийный режим
- `switch.energy_arbitrage_force_charge` - Принудительная зарядка батареи

### Селекторы и настройки

- `select.energy_arbitrage_strategy` - Выбор стратегии арбитража
- `number.energy_arbitrage_min_arbitrage_depth` - Минимальная глубина арбитража (20-80%)
- Другие настраиваемые параметры через UI

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

## 🧠 Предиктивная логика работы

### Новая архитектура системы

Система использует **трехуровневую предиктивную архитектуру**:

```
🔮 EnergyBalancePredictor → ⏰ TimeWindowAnalyzer → 🎯 StrategicPlanner → 🎲 Optimizer
```

#### 1️⃣ **EnergyBalancePredictor** - Прогноз энергетического баланса

- Анализирует прогнозы PV от Solcast на сегодня и завтра
- Оценивает потребление дома
- Определяет энергетические излишки/дефициты
- Рекомендует стратегии: `charge_aggressive`, `charge_moderate`, `sell_aggressive`, `sell_partial`, `hold`

#### 2️⃣ **TimeWindowAnalyzer** - Анализ временных окон

- Находит оптимальные ценовые окна из MQTT данных
- Определяет точные временные рамки для операций
- Рассчитывает временное давление (`high`, `medium`, `low`)
- Планирует операции с учетом мощности батареи

#### 3️⃣ **StrategicPlanner** - Стратегическое планирование

- Создает 24-48 часовые планы операций
- Определяет сценарии: `energy_critical_deficit`, `surplus_both_days`, `transition_periods`
- Оптимизирует последовательность операций
- Создает резервные планы для рискованных сценариев

### Новая иерархия принятия решений

#### 🎯 **ПРИОРИТЕТ 1: Стратегические решения** (confidence ≥ 0.8)

```
🎯 STRATEGIC: Critical charging: 3000Wh needed for energy deficit
```

#### ⏰ **ПРИОРИТЕТ 2: Временные критические** (time_pressure = high)

```
⏰ TIME CRITICAL: Buy window ending in 0.5h (Price: 0.145)
```

#### ⚡ **ПРИОРИТЕТ 3: Предиктивные запланированные**

```
⚡ PLANNED: Today needs battery (Time: 2.1h, ROI: 16.3%)
```

#### 📊 **ПРИОРИТЕТ 4: Предиктивные стандартные**

```
📊 STANDARD: Energy balance today (ROI: 12.8%)
```

#### 💰 **ПРИОРИТЕТ 5: Традиционный арбитраж** (fallback)

```
💰 TRADITIONAL: Good buy opportunity (ROI: 18.2%)
```

#### 🔄 **По умолчанию: Умное удержание**

```
🎯 STRATEGIC HOLD: Planning for tomorrow deficit. Next: buy in 2.3h
```

### Предварительные проверки безопасности

1. **Лимит дневных циклов батареи**

   - Проверка: `today_cycles ≥ max_daily_cycles` (по умолчанию 2.0)
   - Если превышен → `HOLD` (остановка операций)

2. **Минимальная глубина арбитража**
   - Проверка: `battery_level ≥ min_arbitrage_depth` (настраивается 20-80%, по умолчанию 40%)
   - Если ниже → `HOLD` (защита батареи)

### Интеллектуальные сценарии планирования

#### 🔴 **Критический энергетический дефицит**

- Срочная зарядка в лучших ценовых окнах
- Приоритет времени над прибылью
- Использование до 3-х ценовых окон

#### 🟢 **Энергетический излишек обоих дней**

- Консервативная продажа излишков
- Сохранение 50%+ уровня батареи
- Продажа только в топ-2 ценовых окна

#### 🔄 **Переходные сценарии**

- `surplus_today → deficit_tomorrow`: Продажа утром + зарядка вечером
- `deficit_today → surplus_tomorrow`: Зарядка сегодня + подготовка к продаже

#### 💡 **Оппортунистическое планирование**

- Использование ценовых возможностей при стабильном балансе
- Умеренные операции до 2 кВт⋅ч
- Баланс между прибылью и стабильностью

**🔄 Остальные операции выполняет инвертер автоматически:**

- **Зарядка от солнца:** Инвертер сам управляет зарядкой батареи от PV
- **Экспорт излишков:** Инвертер сам экспортирует излишки в сеть
- **Покрытие нагрузки:** Инвертер сам разряжает батарею для покрытия потребления

_Система арбитража фокусируется исключительно на торговых операциях_

### Ключевые параметры

| Параметр                  | Значение | Назначение                               |
| ------------------------- | -------- | ---------------------------------------- |
| **Min Arbitrage Margin**  | 15%      | Минимальная прибыль для арбитража        |
| **Max Daily Cycles**      | 2.0      | Защита батареи от износа                 |
| **Min Arbitrage Depth**   | 40%      | Минимальный уровень для арбитража        |
| **Max Battery Power**     | 5000W    | Максимальная мощность батареи            |
| **Strategic Plan Update** | 30 мин   | Частота обновления стратегических планов |
| **Time Window Analysis**  | 24ч      | Горизонт анализа ценовых окон            |
| **Planning Horizon**      | 48ч      | Горизонт стратегического планирования    |

### 🔍 Алгоритм предиктивного анализа

1. **Энергетический прогноз** (EnergyBalancePredictor):

   - Получение PV прогнозов от Solcast
   - Расчет энергетического баланса на 24-48ч
   - Определение стратегии: charge/sell/hold

2. **Анализ временных окон** (TimeWindowAnalyzer):

   - Поиск последовательных периодов низких/высоких цен
   - Расчет доступной энергии для каждого окна
   - Определение временного давления

3. **Стратегическое планирование** (StrategicPlanner):

   - Создание последовательности операций на 24-48ч
   - Оптимизация с учетом ограничений батареи
   - Резервные планы для рискованных сценариев

4. **Выполнение решений** (ArbitrageOptimizer):
   - Иерархическое принятие решений
   - Адаптация к изменениям в реальном времени
   - Мониторинг выполнения планов

### Режимы работы инвертора

#### Арбитражная зарядка (`charge_arbitrage`)

- `Grid Charging`: `True` (зарядка с сети)
- `Export Surplus`: `False` (не экспортировать)
- `Time of Use`: `Disabled` (отключить ToU)
- `Work Mode`: Стандартный режим

#### Арбитражная продажа (`sell_arbitrage`)

- `Work Mode`: `Export First` (приоритет экспорта)
- `Grid Charging`: `False` (не заряжать с сети)
- `Export Surplus`: `True` (экспортировать излишки)
- `Time of Use`: `Enabled` (использовать ToU)

#### Режим ожидания (`hold`)

- `Time of Use`: `Enabled` (включить ToU)
- `Work Mode`: `Zero Export To Load` (самопотребление)
- `Export Surplus`: `True` (экспортировать излишки)
- `Grid Charging`: `False` (не заряжать с сети)

### Защитные механизмы

- **Минимальный резерв батареи**: 20% (настраивается)
- **Cooldown между действиями**: 5 минут
- **Аварийный режим**: Сохранение заряда батареи
- **Ручное управление**: Временное отключение автоматики

## Мониторинг в Home Assistant

### Пример карточки дашборда

```yaml
type: entities
title: Energy Arbitrage - Основное
entities:
  - sensor.energy_arbitrage_status
  - sensor.energy_arbitrage_next_action
  - sensor.energy_arbitrage_target_power
  - sensor.energy_arbitrage_profit_forecast
  - sensor.energy_arbitrage_roi
  - switch.energy_arbitrage_enabled
  - switch.energy_arbitrage_emergency_mode
  - select.energy_arbitrage_strategy

---
type: entities
title: Energy Arbitrage - Предиктивный анализ
entities:
  - sensor.energy_arbitrage_energy_forecast
  - sensor.energy_arbitrage_price_windows
  - sensor.energy_arbitrage_strategic_plan
  - number.energy_arbitrage_min_arbitrage_depth
  - switch.energy_arbitrage_force_charge
```

### Автоматизации

#### Уведомления о стратегических операциях

```yaml
automation:
  - alias: 'Strategic Plan Notification'
    trigger:
      - platform: state
        entity_id: sensor.energy_arbitrage_strategic_plan
        to: 'executing'
    action:
      - service: notify.telegram
        data:
          message: >
            🎯 Стратегический план активирован!
            Сценарий: {{ state_attr('sensor.energy_arbitrage_strategic_plan', 'scenario') }}
            Прибыль: {{ state_attr('sensor.energy_arbitrage_strategic_plan', 'expected_profit') }}

  - alias: 'Time Critical Opportunity'
    trigger:
      - platform: state
        entity_id: sensor.energy_arbitrage_price_windows
        attribute: time_pressure
        to: 'high'
    action:
      - service: notify.telegram
        data:
          message: >
            ⏰ Критическое ценовое окно!
            Действие: {{ state_attr('sensor.energy_arbitrage_price_windows', 'current_action') }}
            Время: {{ state_attr('sensor.energy_arbitrage_price_windows', 'time_remaining') }}
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

- Проверьте настройку минимальной маржи (по умолчанию 15%)
- Убедитесь в корректности прогноза тарифов через MQTT
- Проверьте уровень заряда батареи и минимальную глубину арбитража
- Убедитесь в корректности Solcast прогнозов PV
- Проверьте настройку максимальной мощности батареи

### Проблемы с предиктивной системой

- **Energy Forecast показывает "error"**: Проверьте доступность Solcast сенсоров
- **Price Windows показывает "no_windows"**: Проверьте MQTT данные и их формат
- **Strategic Plan показывает "no_active_plan"**: Система создает план каждые 30 минут
- **Низкая confidence в планах**: Улучшите качество входных данных (PV прогнозы, цены)

## Поддержка

- **Issues**: [GitHub Issues](https://github.com/rviar/ha-energy-arbitrage/issues)
- **Документация**: [Wiki](https://github.com/rviar/ha-energy-arbitrage/wiki)
- **Community**: [Home Assistant Community Forum](https://community.home-assistant.io/)

## Лицензия

MIT License - см. [LICENSE](LICENSE) файл.

## Changelog

### v2.0.0 - Предиктивная система 🧠

- ✨ **Предиктивная архитектура**: EnergyBalancePredictor + TimeWindowAnalyzer + StrategicPlanner
- 🎯 **Стратегическое планирование**: Долгосрочные планы на 24-48 часов
- ⏰ **Анализ временных окон**: Точные периоды для операций с временным давлением
- 📊 **Новые сенсоры**: Energy Forecast, Price Windows, Strategic Plan
- 🎛️ **Настраиваемая глубина арбитража**: Min Arbitrage Depth (20-80%)
- ⚙️ **Конфигурируемые entity ID**: Time of Use и Export Surplus
- 🔄 **Упрощенная логика**: Убрано управление солнечной энергией (делегировано инвертеру)
- 🎲 **Иерархия решений**: 5-уровневая система приоритетов
- 🛡️ **Резервные планы**: Для критических сценариев

### v1.0.0

- Первый релиз
- Базовый функционал арбитража
- MQTT интеграция для тарифов
- UI конфигурация
- Полный набор сенсоров и сервисов
