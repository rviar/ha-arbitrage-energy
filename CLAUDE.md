# Промпт для Claude Code: Создание Energy Arbitrage Integration для Home Assistant

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
- Интервал пересчета (минуты, по умолчанию 15)
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

### 6. Продвинутый алгоритм арбитража с использованием батареи:

1. **Анализ арбитражных возможностей каждые 15 минут:**
   ```python
   def find_arbitrage_opportunities():
       current_sell_price = get_current_sell_price()
       current_buy_price = get_current_buy_price()
       price_forecast_24h = get_price_forecast()
       
       # Найти окна высоких и низких цен
       high_price_windows = find_price_peaks(price_forecast_24h)
       low_price_windows = find_price_valleys(price_forecast_24h)
       
       # Найти прибыльные пары sell_high -> buy_low
       arbitrage_ops = match_sell_buy_windows(high_price_windows, low_price_windows)
       
       return filter_profitable_ops(arbitrage_ops, min_roi_threshold)
   ```

2. **Расчет прибыльности арбитража:**
   ```python
   def calculate_arbitrage_roi(sell_price, buy_price, hours_between):
       # Учесть потери батареи при цикле заряд-разряд
       battery_efficiency = 0.90  # 90% эффективность
       
       # Учесть риск изменения прогноза цен
       price_risk_factor = max(0.95, 1 - hours_between * 0.02)
       
       gross_profit = sell_price - buy_price
       net_profit = gross_profit * battery_efficiency * price_risk_factor
       
       roi = (net_profit / buy_price) * 100
       return roi
   ```

3. **Логика принятия решений:**
   ```python
   def decide_action():
       battery_level = get_battery_level()
       solar_surplus = get_solar_surplus()
       current_price = get_current_price()
       
       # Проверить активные арбитражные возможности
       best_arbitrage = find_best_arbitrage_opportunity()
       
       if best_arbitrage and best_arbitrage.roi > MIN_ROI:
           if best_arbitrage.action == 'sell_now':
               # ПРОДАВАТЬ даже из батареи если ROI высокий
               if battery_level > EMERGENCY_RESERVE:
                   return 'SELL_ARBITRAGE'
           
           elif best_arbitrage.action == 'buy_now':
               # ПОКУПАТЬ для подготовки к продаже
               if battery_level < MAX_CAPACITY:
                   return 'CHARGE_ARBITRAGE'
       
       # Стандартная логика без арбитража
       if solar_surplus > 0:
           if battery_level < 95%:
               return 'CHARGE_BATTERY'  # Сначала зарядить батарею
           else:
               return 'SELL_SURPLUS'    # Продать избыток
       
       return 'HOLD'
   ```

4. **Управление рисками:**
   ```python
   # КРИТЕРИИ для продажи из батареи:
   if (arbitrage_roi > MIN_ROI AND 
       battery_level > EMERGENCY_RESERVE + 20% AND
       buy_opportunity_within_hours < MAX_HOLD_TIME AND
       price_forecast_confidence > 0.7):
       allow_battery_arbitrage = True
   
   # ЗАЩИТА от потерь:
   if time_since_arbitrage_start > MAX_HOLD_TIME:
       force_close_position = True  # Закрыть позицию принудительно
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
- Предусмотри fallback варианты если какие-то данные недоступны
- Добавь режим обучения для улучшения прогнозов потребления
- Реализуй уведомления о выгодных арбитражных возможностях
- Создай детальное логирование всех решений для анализа

**ВАЖНО:** Не делай предположений о том, какие entity_id или интеграции я использую. Всегда спрашивай!