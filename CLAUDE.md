Создай кастомную интеграцию для Home Assistant через HACS для автоматизированного энергетического арбитража с солнечными панелями и батареями.

## Требования к функциональности:

### 1. Основной алгоритм арбитража:

- Анализировать прогноз солнечной генерации на 24-48 часов
- Прогнозировать домашнее потребление на основе исторических данных
- Получать почасовые тарифы на электроэнергию (покупка/продажа)
- Находить выгодные окна для продажи дорого и покупки дешево
- Учитывать текущий заряд батареи и технические ограничения
- Обеспечивать минимальный резерв энергии для критических нужд

### 2. Структура интеграции:

```
custom_components/energy_arbitrage/
├── __init__.py
├── manifest.json
├── config_flow.py
├── const.py
├── coordinator.py
├── sensor.py
├── switch.py
├── services.yaml
└── arbitrage/
    ├── predictor.py     # Модуль прогнозирования
    ├── optimizer.py     # Оптимизатор арбитража
    ├── executor.py      # Исполнитель решений
    └── utils.py         # Вспомогательные функции
```

### 3. Конфигурация через UI:

**Солнечная система:**

- Сенсор прогноза генерации (entity_id)
- Максимальная мощность панелей (кВт)

**Батарейная система:**

- Сенсор уровня заряда батареи (%)
- Максимальная емкость батареи (кВт⋅ч)
- Минимальный резерв заряда (%, по умолчанию 20%)
- Эффективность заряда/разряда (%, по умолчанию 90%)
- Максимальная мощность заряда/разряда (кВт)

**Энергосистема:**

- Сенсор текущего потребления (кВт)
- Сенсор почасовых тарифов покупки
- Сенсор почасовых тарифов продажи
- Максимальная мощность продажи в сеть (кВт)

**Алгоритм:**

- Горизонт планирования (часы, по умолчанию 24)
- Интервал пересчета (минуты, по умолчанию 1)
- Минимальная маржа арбитража (%, по умолчанию 5%)
- Приоритет самопотребления (bool, по умолчанию true)

### 4. Создаваемые сенсоры:

```yaml
sensor.energy_arbitrage_next_action        # Следующее действие (charge/discharge/hold)
sensor.energy_arbitrage_target_power       # Целевая мощность заряда/разряда
sensor.energy_arbitrage_profit_forecast    # Прогноз прибыли за 24 часа
sensor.energy_arbitrage_battery_target     # Целевой уровень заряда батареи
sensor.energy_arbitrage_sell_window        # Начало следующего окна продажи
sensor.energy_arbitrage_buy_window         # Начало следующего окна покупки
```

### 5. Переключатели и сервисы:

```yaml
switch.energy_arbitrage_enabled             # Включение/выключение арбитража
switch.energy_arbitrage_emergency_mode      # Аварийный режим (только резерв)

# Сервисы:
energy_arbitrage.recalculate               # Принудительный пересчет
energy_arbitrage.set_battery_reserve       # Изменить минимальный резерв
energy_arbitrage.manual_override           # Ручное управление на N часов
```

### 7. Технические требования:

- Использовать `DataUpdateCoordinator` для управления обновлениями
- Логирование всех решений и их обоснований
- Обработка ошибок и восстановление после сбоев
- Валидация входных данных и предотвращение некорректных команд
- Интеграция с существующими инверторными системами через стандартные протоколы
- Веб-интерфейс для мониторинга и настройки параметров

### 8. Безопасность и надежность:

- Автоматическое отключение при обнаружении аномалий
- Ограничение максимальной мощности операций
- Резервный режим при потере связи с инвертором
- Защита от глубокого разряда батареи
- Логирование всех операций для аудита

### 9. Файлы для HACS:

```json
// manifest.json
{
  "domain": "energy_arbitrage",
  "name": "Energy Arbitrage",
  "documentation": "https://github.com/username/ha-energy-arbitrage",
  "dependencies": [],
  "codeowners": ["@username"],
  "requirements": ["numpy", "pandas", "scikit-learn"],
  "version": "1.0.0"
}
```

Создай полнофункциональную интеграцию с подробными комментариями, примерами конфигурации и документацией для пользователей. Интеграция должна быть готова к установке через HACS и немедленному использованию после настройки базовых параметров.

## Дополнительные пожелания:

**ПРОЦЕСС РАЗРАБОТКИ:**

1. **Начни с детального опроса** - задай все вопросы о моих entity_id и источниках данных
2. **Покажи диаграмму архитектуры** с конкретными entity_id после получения ответов
3. **Предложи дополнительные опции** на основе доступных данных
4. **Создай адаптированную интеграцию** под мою конкретную систему

**ФУНКЦИОНАЛЬНОСТЬ:**

- Добавь возможность экспорта данных для анализа эффективности
- Создай простой веб-дашборд для мониторинга
- Добавь режим обучения для улучшения прогнозов потребления
- Реализуй уведомления о выгодных арбитражных возможностях
- Создай детальное логирование всех решений для анализа

**ВАЖНО:** Не делай предположений о том, какие entity_id или интеграции я использую. Всегда спрашивай!

## Требования к архитектуре интеграции:

### ПРИНЦИП РАЗДЕЛЕНИЯ ДАННЫХ И ЛОГИКИ:

1. **Все данные должны быть доступны через сенсоры:**

   - Входные данные (цены, мощности, уровень батареи) → Input Data Sensors
   - Параметры конфигурации → Configuration Parameter Sensors
   - Выходные данные решений → Output/Decision Sensors

2. **Алгоритм арбитража должен использовать только данные из сенсоров:**

   - Не напрямую из entity_id других интеграций
   - Не из конфигурационных файлов
   - Только через стандартизованные сенсоры интеграции

3. **Структура сенсоров:**

   **Input Data Sensors (входные данные):**

   ```yaml
   sensor.energy_arbitrage_current_buy_price      # Текущая цена покупки
   sensor.energy_arbitrage_current_sell_price     # Текущая цена продажи
   sensor.energy_arbitrage_min_buy_price_24h      # Минимальная цена покупки за 24ч
   sensor.energy_arbitrage_max_sell_price_24h     # Максимальная цена продажи за 24ч
   sensor.energy_arbitrage_input_battery_level    # Уровень заряда батареи
   sensor.energy_arbitrage_input_pv_power         # Текущая мощность PV
   sensor.energy_arbitrage_input_load_power       # Текущая мощность нагрузки
   sensor.energy_arbitrage_input_grid_power       # Текущая мощность сети
   sensor.energy_arbitrage_pv_forecast_today      # Прогноз PV на сегодня
   sensor.energy_arbitrage_pv_forecast_tomorrow   # Прогноз PV на завтра
   sensor.energy_arbitrage_available_battery_capacity  # Доступная емкость батареи
   sensor.energy_arbitrage_net_consumption        # Чистое потребление (нагрузка - PV)
   sensor.energy_arbitrage_surplus_power          # Избыток мощности (PV - нагрузка)
   ```

   **Configuration Parameter Sensors (параметры конфигурации):**

   ```yaml
   sensor.energy_arbitrage_config_min_arbitrage_margin    # Мин. маржа арбитража (%)
   sensor.energy_arbitrage_config_planning_horizon        # Горизонт планирования (часы)
   sensor.energy_arbitrage_config_max_daily_cycles        # Макс. циклов в день
   sensor.energy_arbitrage_config_battery_efficiency      # Эффективность батареи (%)
   sensor.energy_arbitrage_config_min_battery_reserve     # Мин. резерв батареи (%)
   sensor.energy_arbitrage_config_max_battery_power       # Макс. мощность батареи (кВт)
   sensor.energy_arbitrage_config_battery_capacity        # Емкость батареи (кВт⋅ч)
   ```

   **Output/Decision Sensors (выходные данные решений):**

   ```yaml
   sensor.energy_arbitrage_next_action            # Следующее действие
   sensor.energy_arbitrage_target_power           # Целевая мощность
   sensor.energy_arbitrage_profit_forecast        # Прогноз прибыли
   sensor.energy_arbitrage_battery_target         # Целевой уровень батареи
   sensor.energy_arbitrage_roi                    # Ожидаемый ROI
   sensor.energy_arbitrage_next_buy_window        # Следующее окно покупки
   sensor.energy_arbitrage_next_sell_window       # Следующее окно продажи
   ```

4. **Преимущества такой архитектуры:**

   - **Прозрачность:** Все данные видны в UI Home Assistant
   - **Отладка:** Легко отследить какие данные использует алгоритм
   - **Тестирование:** Можно подставить тестовые значения через сенсоры
   - **Мониторинг:** Пользователь видит все входные и выходные данные
   - **Настройка:** Все параметры доступны через UI
   - **Логирование:** Автоматическое логирование изменений через HA

5. **Обновление данных:**

   - Coordinator собирает данные из источников (entity_id, MQTT)
   - Обновляет Input Data Sensors
   - Configuration Parameter Sensors обновляются при изменении настроек
   - Алгоритм арбитража читает данные из сенсоров и обновляет Decision Sensors

6. **Код алгоритма должен выглядеть так:**

   ```python
   def calculate_optimal_action(self):
       # Читаем входные данные из сенсоров
       current_buy_price = self.get_sensor_value("current_buy_price")
       current_sell_price = self.get_sensor_value("current_sell_price")
       battery_level = self.get_sensor_value("input_battery_level")

       # Читаем параметры конфигурации из сенсоров
       min_margin = self.get_sensor_value("config_min_arbitrage_margin")
       planning_horizon = self.get_sensor_value("config_planning_horizon")

       # Выполняем расчеты
       decision = self.optimize_arbitrage(...)

       # Обновляем выходные сенсоры через coordinator
       return decision
   ```

**ЭТО КРИТИЧЕСКИ ВАЖНО:** Весь алгоритм должен работать только с данными из сенсоров, а не напрямую из конфигурации или внешних entity_id!
