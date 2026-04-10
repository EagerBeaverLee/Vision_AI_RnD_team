import dash
from dash import dcc, html
import plotly.express as px
import pandas as pd

# 샘플 데이터 생성 (시간 열 추가)
data = {
    '시간': ['08:00', '09:00', '10:00'],
    'GUST풍속(m/s)': [6.1, 8.7, 9.2],
    '현지기압(hPa)': [1018.9, 1018.5, 1018.2],
    '수온(°C)': [15.3, 15.3, 15.3],
    '최대파고(m)': [3.1, 2.9, 2.9],
    '유의파고(m)': [2.3, 2.1, 1.9],
    '평균파고(m)': [1.3, 1.3, 1.1],
    '파주기(sec)': [6.9, 6.8, 6.7],
    '파향(deg)': [348, 332, 355]
}
df = pd.DataFrame(data)

# 앱 초기화
app = dash.Dash(__name__)

# 그래프 생성
fig_wind = px.line(df, x='시간', y='GUST풍속(m/s)', title='시간별 풍속 변화')
fig_pressure = px.line(df, x='시간', y='현지기압(hPa)', title='시간별 기압 변화')
fig_waves = px.line(df, x='시간', y=['최대파고(m)', '유의파고(m)', '평균파고(m)'], title='시간별 파고 변화')

# 레이아웃 설정
app.layout = html.Div(children=[
    html.H1(children='해양 기상 데이터 대시보드'),

    html.Div([
        html.Div([
            dcc.Graph(id='wind-graph', figure=fig_wind)
        ], className="six columns"),

        html.Div([
            dcc.Graph(id='pressure-graph', figure=fig_pressure)
        ], className="six columns"),
    ], className="row"),

    html.Div([
        dcc.Graph(id='wave-graph', figure=fig_waves)
    ])
])

if __name__ == '__main__':
    # app.run_server(debug=True)
    app.run(debug=True)