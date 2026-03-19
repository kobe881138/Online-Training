import streamlit as st
import pandas as pd
import requests
import time

# 設定網頁標題與排版
st.set_page_config(page_title="選手訓練與健康監控", layout="centered")

# ==========================================
# 1. 系統設定參數 (⚠️ 請確保這裡填入正確的資料)
# ==========================================
SHEET_ID = "1fZDVVu0rQ30DUQxArY5FUQ14X4UZZ-ZszkJQpY_Fg1k"
EXERCISE_GID = "0" 
PROGRAM_GID = "1157647854"  # ⚠️ 務必換成 Program_DB 的純數字 GID
GAS_URL = "https://script.google.com/macros/s/AKfycbzNwRQfKH6Pb0VCq64A-OyYPL40AUpY9ZC6usT1Wy0485EGgVyaKZA3PvkrhxInKJM1Mg/exec"       # ⚠️ 務必換成包含睡眠/飲水功能的新網址

# ==========================================
# 2. 讀取資料函數 (包含錯誤防護)
# ==========================================
@st.cache_data(ttl=60)
def load_data(gid):
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(csv_url)
        df.columns = df.columns.str.strip() 
        return df
    except Exception as e:
        st.error(f"讀取資料庫失敗 (GID: {gid})，錯誤訊息: {e}")
        return pd.DataFrame()

# ==========================================
# 3. 網頁主介面
# ==========================================
st.title("⚡ 選手每日訓練與狀態回報")

user_email = st.text_input("請輸入您的專屬 Email 載入今日課表：").strip().lower()

if user_email:
    # 載入資料庫
    df_exercise = load_data(EXERCISE_GID)
    df_program = load_data(PROGRAM_GID)
    
    if not df_program.empty:
        # 統一小寫並過濾該學生的 Pending 課表
        df_program['Status'] = df_program['Status'].astype(str).str.strip().str.lower()
        my_workout = df_program[(df_program['Email'].str.lower() == user_email) & (df_program['Status'] == 'pending')]
        
        if my_workout.empty:
            st.success("🎉 太棒了！今日課表已全部完成，請好好休息！")
            if st.button("🔄 重新整理檢查新課表"):
                st.cache_data.clear()
                st.rerun()
        else:
            # ==========================================
            # 區塊一：每日健康數據
            # ==========================================
            st.subheader("🌙 每日恢復狀態")
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                sleep_hr = st.number_input("昨晚睡眠時間 (小時)", min_value=0.0, max_value=24.0, value=7.0, step=0.5)
            with col_h2:
                water_cc = st.number_input("今日飲水量 (cc)", min_value=0, max_value=10000, value=2000, step=100)
            
            st.divider()
            st.subheader("🔥 今日訓練內容")

            # ==========================================
            # 區塊二：訓練動態表單
            # ==========================================
            with st.form("workout_form"):
                for index, row in my_workout.iterrows():
                    movement_name = str(row['Movement']).strip()
                    st.markdown(f"#### {row['Order']}. {movement_name}")
                    st.caption(f"🎯 目標：{row['Sets']} 組 x {row['Reps']} | 強度：{row['Intensity']}")
                    
                    # 抓取影片
                    if not df_exercise.empty:
                        video_info = df_exercise[df_exercise['Movement'].str.strip() == movement_name]
                        if not video_info.empty:
                            video_url = video_info['Demonstration'].iloc[0]
                            if pd.notna(video_url) and str(video_url).startswith("http"):
                                with st.expander("📺 點擊查看示範影片"):
                                    st.video(video_url)
                    
                    # 抓取 Trackmode 決定輸入框外觀
                    track_mode = str(row.get('Trackmode', 'Weight+Reps')).strip()
                    rpe_options = ["<5", "5", "6", "7", "8", "9", "10"]
                    
                    c1, c2, c3 = st.columns(3)
                    
                    if track_mode == 'Reps':
                        with c1: st.number_input("完成次數", min_value=0, step=1, key=f"reps_{index}")
                        with c2: st.selectbox("RPE (自覺強度)", rpe_options, index=3, key=f"rpe_{index}")
                    elif track_mode == 'Time':
                        with c1: st.number_input("完成秒數", min_value=0, step=5, key=f"time_{index}")
                        with c2: st.selectbox("RPE (自覺強度)", rpe_options, index=3, key=f"rpe_{index}")
                    else: # 預設 Weight+Reps
                        with c1: st.number_input("重量 (kg)", min_value=0.0, step=2.5, key=f"weight_{index}")
                        with c2: st.number_input("完成次數", min_value=0, step=1, key=f"reps_{index}")
                        with c3: st.selectbox("RPE (自覺強度)", rpe_options, index=3, key=f"rpe_{index}")
                    
                    st.markdown("---")
                
                # 區塊三：訓練總結 (放在表單最底端)
                st.subheader("⏱️ 訓練總結")
                duration = st.number_input("本次訓練總時長 (分鐘)", min_value=1, max_value=300, value=60, step=5)
                
                # 送出按鈕
                submitted = st.form_submit_button("✅ 辛苦了！一次送出所有紀錄")

            # ==========================================
            # 區塊四：送出資料的邏輯處理 (嚴格對齊 form 外側)
            # ==========================================
            if submitted:
                with st.spinner('正在安全同步數據到資料庫，請稍候...'):
                    success_count = 0
                    total_moves = len(my_workout)
                    
                    for index, row in my_workout.iterrows():
                        # 使用 .get 安全抓取 session_state，避免當機
                        track_mode = str(row.get('Trackmode', 'Weight+Reps')).strip()
                        actual_rpe = str(st.session_state.get(f"rpe_{index}", "7"))
                        
                        if track_mode == 'Reps':
                            w = "自體重"
                            r = str(st.session_state.get(f"reps_{index}", "0"))
                        elif track_mode == 'Time':
                            w = "等長收縮"
                            r = str(st.session_state.get(f"time_{index}", "0")) + "秒"
                        else:
                            w = str(st.session_state.get(f"weight_{index}", "0.0"))
                            r = str(st.session_state.get(f"reps_{index}", "0"))

                        # 打包上傳資料
                        payload = {
                            "email": user_email,
                            "day": str(row['Day']),
                            "movement": str(row['Movement']).strip(),
                            "weight": w,
                            "reps": r,
                            "rir": actual_rpe,  # 後端接收欄位維持 rir，內容傳 rpe
                            "sleep": sleep_hr,
                            "water": water_cc,
                            "duration": duration
                        }
                        
                        try:
                            # 加入 timeout 避免無限轉圈圈
                            res = requests.post(GAS_URL, json=payload, timeout=10)
                            if res.status_code == 200:
                                success_count += 1
                            else:
                                st.error(f"寫入失敗 ({row['Movement']}): {res.text}")
                        except Exception as e:
                            st.error(f"網路連線異常 ({row['Movement']}): {e}")
                    
                    # 結算與畫面更新
                    if success_count == total_moves:
                        st.balloons()
                        st.success(f"✅ 完美！今日 {success_count} 項動作已全數記錄。")
                        time.sleep(2)
                        st.cache_data.clear()
                        st.rerun()
                    elif success_count > 0:
                        st.warning(f"⚠️ 只有部分成功，已完成 {success_count}/{total_moves}。請檢查網路後重試。")