# -*- coding: utf-8 -*-
"""
一键启动脚本: main.py
描述: 
    videoMVP 视频智能重绘与分镜重构工作流的统一入口。
    一键顺序运行完整流水线：
      1. 物理分切视频 (split_video.py)
      2. 关键帧提取与分镜要素提取 (generate_storyboard.py)
      3. 脑暴 3 种创意大纲 (generate_creative_storylines.py)
      4. 智能方案评估、资产生图提示词生成、新剧本改写及视频重绘提示词编译 (evaluate_storylines.py)
"""
import os
import sys
import subprocess
import time

def print_header(title):
    print("=" * 70)
    print(f"* {title} *".center(70))
    print("=" * 70)

def run_script(script_name, args=[]):
    script_path = os.path.join("scripts", script_name)
    if not os.path.exists(script_path):
        print(f"[错误] 未找到脚本文件: {script_path}")
        sys.exit(1)
        
    cmd = [sys.executable, script_path] + args
    print(f"[Run] 正在运行: {' '.join(cmd)}")
    
    # 捕获并实时流式输出日志，使用 sys.stdout.encoding 保证与当前控制台终端一致，并容错处理
    console_encoding = sys.stdout.encoding or "utf-8"
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding=console_encoding, errors="replace")
    
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
            
    rc = process.poll()
    if rc != 0:
        print(f"\n[ERROR] [异常] {script_name} 运行失败，退出码: {rc}")
        sys.exit(rc)
    print(f"[SUCCESS] [成功] {script_name} 执行完毕！\n")

def main():
    print_header("videoMVP 视频智能重绘全流程工作流 (One-Click Pipeline)")
    
    # 检查 API Key
    api_key = os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # 尝试读取 .env 文件
        dotenv_path = ".env"
        if os.path.exists(dotenv_path):
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "T8STAR_API_KEY":
                            api_key = v.strip().strip("'\"")
                            os.environ["T8STAR_API_KEY"] = api_key
                            break
                            
    if not api_key:
        print("[错误] 未检测到大模型 API Key！")
        print("请在项目根目录下创建 .env 文件并配置：T8STAR_API_KEY=your_key_here")
        sys.exit(1)
        
    start_time = time.time()
    
    # Step 1: 镜头切分
    print_header("Step 1: 物理切分视频 (split_video.py)")
    run_script("split_video.py")
    
    # Step 2: 提取关键帧与分镜识别
    print_header("Step 2: 提取关键帧与分镜识别 (generate_storyboard.py)")
    run_script("generate_storyboard.py")
    
    # Step 3: 故事大纲脑暴
    print_header("Step 3: 创意故事大纲脑暴 (generate_creative_storylines.py)")
    run_script("generate_creative_storylines.py")
    
    # Step 4: 评估最优大纲，自动输出视觉提示词，并触发剧本改写与重绘提示词编译
    print_header("Step 4-6: 智能方案评估、资产提示词导出与改写流程 (evaluate_storylines.py)")
    run_script("evaluate_storylines.py")
    
    duration = time.time() - start_time
    print_header("全流程自动化重构成功！")
    print(f"总计耗时: {duration:.2f} 秒。")
    print("产出结果：")
    print("  1. 智能方案评估报告: output/evaluation_report.md")
    print("  2. MJ/Flux生图参考提示词: output/asset_prompts.md")
    print("  3. 最终视频重绘剧本分镜表: output/storyboard.md")
    print("  4. 最终视频重绘剧本数据表: output/storyboard.csv")
    print("=" * 70)

if __name__ == "__main__":
    main()
