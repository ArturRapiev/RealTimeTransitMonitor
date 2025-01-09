import streamlit as st
import streamlit.components.v1 as components
import folium
from folium.plugins import MarkerCluster
import requests
import gtfs_realtime_pb2
from datetime import datetime
import pandas as pd
import time
import plotly.express as px
import logging
import os

# Настройка логирования
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)  # Создаём директорию для логов, если её нет
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Функция для управления файлами логов
def manage_log_files(directory, max_files):
    log_files = sorted(
        [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".log")],
        key=os.path.getmtime
    )
    while len(log_files) > max_files:
        os.remove(log_files.pop(0))
        logging.info("Удалён старый файл лога")

manage_log_files(LOG_DIR, 5)  # Ограничиваем количество логов до 5

# Функция для загрузки и декодирования данных GTFS-RT
def get_vehicle_positions(url):
    logging.info("Начата загрузка данных из GTFS-RT")
    response = requests.get(url)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    vehicles = []
    for entity in feed.entity:
        if entity.HasField("vehicle"):
            vehicle = entity.vehicle
            vehicles.append({
                "vehicle_id": vehicle.vehicle.id,
                "route_id": vehicle.trip.route_id,
                "latitude": vehicle.position.latitude,
                "longitude": vehicle.position.longitude,
                "speed": vehicle.position.speed if vehicle.position.HasField("speed") else None,
                "timestamp": datetime.fromtimestamp(vehicle.timestamp).strftime(
                    '%Y-%m-%d %H:%M:%S') if vehicle.timestamp else None
            })
    logging.info(f"Загружено {len(vehicles)} транспортных средств")
    return pd.DataFrame(vehicles)


# Основная функция Streamlit
def main():
    logging.info("Приложение запущено")
    st.title("Мониторинг транспорта в реальном времени")

    # URL GTFS-RT
    gtfs_rt_url = "http://gtfs.ltconline.ca/Vehicle/VehiclePositions.pb" # Впишите сюда адрес gtfs файла

    # Настройки
    st.sidebar.header("Настройки")
    refresh_rate = st.sidebar.slider("Частота обновления (секунды)", 5, 60, 15)

    st.write(f"Данные обновляются каждые {refresh_rate} секунд.")
    st.write("Источник данных:", gtfs_rt_url)

    # Создаём контейнеры для таблицы, карты, графика и таймера
    table_placeholder = st.empty()
    map_placeholder = st.empty()
    graph_placeholder = st.empty()
    countdown_placeholder = st.sidebar.empty()

    # Сохраняем выбор маршрута
    if "selected_route" not in st.session_state:
        st.session_state.selected_route = "Все"

    # Загружаем данные
    with st.spinner("Загружаем данные..."):
        data = get_vehicle_positions(gtfs_rt_url)

    if not data.empty:
        # Генерируем список маршрутов один раз
        unique_routes = ["Все"] + sorted(data['route_id'].dropna().unique())

        # Выбор маршрута (вызывается один раз вне цикла)
        st.session_state.selected_route = st.sidebar.selectbox(
            "Выберите маршрут:",
            unique_routes,
            key="route_selector",
            index=unique_routes.index(st.session_state.selected_route)
            if st.session_state.selected_route in unique_routes else 0
        )

    while True:
        if not data.empty:
            # Фильтрация данных по маршруту
            if st.session_state.selected_route != "Все":
                filtered_data = data[data['route_id'] == st.session_state.selected_route]
                logging.info(f"Выбран маршрут: {st.session_state.selected_route}")
            else:
                filtered_data = data
                logging.info("Выбраны все маршруты")

            # Обновляем таблицу
            with table_placeholder.container():
                st.subheader("Данные о транспорте")
                st.dataframe(filtered_data)

            # Обновляем карту
            with map_placeholder.container():
                st.subheader("Карта транспорта")
                m = folium.Map(location=[filtered_data['latitude'].mean(), filtered_data['longitude'].mean()], zoom_start=12)
                marker_cluster = MarkerCluster().add_to(m)

                for _, row in filtered_data.iterrows():
                    popup = (
                        f"Vehicle ID: {row['vehicle_id']}<br>"
                        f"Route ID: {row['route_id']}<br>"
                        f"Speed: {row['speed']}<br>"
                        f"Timestamp: {row['timestamp']}"
                    )
                    folium.Marker(
                        location=[row['latitude'], row['longitude']],
                        popup=popup,
                        icon=folium.Icon(color="blue", icon="info-sign")
                    ).add_to(marker_cluster)

                # Отображение карты
                components.html(m._repr_html_(), height=500)

            # Обновляем график скорости
            with graph_placeholder.container():
                st.subheader("График скорости транспортных средств")
                if "speed" in filtered_data.columns and not filtered_data["speed"].isna().all():
                    fig = px.histogram(filtered_data, x="speed", nbins=20, title="Распределение скорости")
                    st.plotly_chart(fig, use_container_width=True, key=f"plotly_chart_{time.time()}")
                    logging.info("График скорости обновлён")
                else:
                    st.write("Нет данных о скорости для построения графика.")
                    logging.warning("Отсутствуют данные о скорости")

        else:
            st.warning("Нет данных для отображения!")
            logging.warning("Данные отсутствуют")

        # Таймер обратного отсчёта
        for seconds in range(refresh_rate, 0, -1):
            countdown_placeholder.write(f"Обновление через: {seconds} секунд")
            time.sleep(1)

        # Обновляем данные
        data = get_vehicle_positions(gtfs_rt_url)
        logging.info("Данные обновлены")


if __name__ == "__main__":
    main()
