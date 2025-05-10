#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
东方财富网A股涨停股票筛选工具
只筛选涨停的股票，固定每天输出10支优选股并排序
"""

import requests
import json
import pandas as pd
import time
import os
import random
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("zt_selector.log", encoding='utf-8', mode='w'),  # 使用'w'模式覆盖旧日志
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ZTSelector:
    def __init__(self, config_file="config.json"):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }
        self.stock_api = 'http://82.push2.eastmoney.com/api/qt/clist/get'
        
        # 加载配置文件
        self.config = self.load_config(config_file)
        
        self.output_dir = self.config["output"]["output_dir"]
        
        # 确保输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def load_config(self, config_file):
        """加载配置文件"""
        # 默认配置，作为备份和参考
        default_config = {
            "filter": {
                "max_price": 40,
                "min_limit_up_percent": 9.5,
                "exclude_st": True,
                "exclude_sci_tech_board": True,
                "stock_prefix": ["0", "6"]
            },
            "score": {
                "base_score": 50,
                "volume_ratio_weight": 5,
                "turnover_rate_weight": 2,
                "continuous_limit_up_weight": 10,
                "amount_weight": 3,
                "amount_max_score": 15
            },
            "output": {
                "top_count": 10,
                "output_dir": "output",
                "auto_open_excel": True
            }
        }
        
        # 储存最终使用的配置
        final_config = default_config.copy()
        
        try:
            if os.path.exists(config_file):
                # 尝试以不同编码读取文件
                encodings = ['utf-8', 'utf-8-sig', 'gbk', 'cp1252']
                file_content = None
                
                for encoding in encodings:
                    try:
                        with open(config_file, 'r', encoding=encoding) as f:
                            file_content = f.read()
                            break
                    except UnicodeDecodeError:
                        continue
                
                if file_content is None:
                    logger.error(f"无法读取配置文件，尝试了以下编码: {encodings}")
                    return default_config
                
                # 解析JSON
                try:
                    loaded_config = json.loads(file_content)
                except json.JSONDecodeError as e:
                    logger.error(f"配置文件JSON格式错误: {e}")
                    return default_config
                
                # 逐层合并配置，使用默认值填充缺失项
                if "filter" in loaded_config:
                    for key, value in loaded_config["filter"].items():
                        if key in default_config["filter"]:
                            final_config["filter"][key] = value
                
                if "score" in loaded_config:
                    for key, value in loaded_config["score"].items():
                        if key in default_config["score"]:
                            final_config["score"][key] = value
                
                if "output" in loaded_config:
                    for key, value in loaded_config["output"].items():
                        if key in default_config["output"]:
                            final_config["output"][key] = value
                
                # 验证重要配置值的类型和范围
                self._validate_config(final_config)
                
                return final_config
            else:
                logger.warning(f"配置文件{config_file}不存在，使用默认配置")
                return default_config
        except Exception as e:
            logger.error(f"加载配置文件出错: {e}")
            return default_config
    
    def _validate_config(self, config):
        """验证配置值的类型和范围"""
        try:
            # 验证filter部分
            filter_config = config["filter"]
            
            # 确保max_price是数值并且为正数
            if not isinstance(filter_config["max_price"], (int, float)) or filter_config["max_price"] <= 0:
                logger.warning(f"max_price应为正数，当前值: {filter_config['max_price']}，使用默认值40")
                filter_config["max_price"] = 40
            
            # 确保min_limit_up_percent是数值并且在合理范围内
            if not isinstance(filter_config["min_limit_up_percent"], (int, float)) or not 0 <= filter_config["min_limit_up_percent"] <= 20:
                logger.warning(f"min_limit_up_percent应在0-20之间，当前值: {filter_config['min_limit_up_percent']}，使用默认值9.5")
                filter_config["min_limit_up_percent"] = 9.5
            
            # 确保exclude_st是布尔值
            if not isinstance(filter_config["exclude_st"], bool):
                logger.warning(f"exclude_st应为布尔值，当前值: {filter_config['exclude_st']}，使用默认值True")
                filter_config["exclude_st"] = True
            
            # 确保exclude_sci_tech_board是布尔值
            if not isinstance(filter_config["exclude_sci_tech_board"], bool):
                logger.warning(f"exclude_sci_tech_board应为布尔值，当前值: {filter_config['exclude_sci_tech_board']}，使用默认值True")
                filter_config["exclude_sci_tech_board"] = True
            
            # 确保stock_prefix是列表并且包含有效值
            if not isinstance(filter_config["stock_prefix"], list) or len(filter_config["stock_prefix"]) == 0:
                logger.warning(f"stock_prefix应为非空列表，当前值: {filter_config['stock_prefix']}，使用默认值['0', '6']")
                filter_config["stock_prefix"] = ["0", "6"]
            
            # 验证score部分
            score_config = config["score"]
            for key in ["base_score", "volume_ratio_weight", "turnover_rate_weight", "continuous_limit_up_weight", "amount_weight", "amount_max_score"]:
                if not isinstance(score_config[key], (int, float)) or score_config[key] < 0:
                    logger.warning(f"{key}应为非负数值，当前值: {score_config[key]}，使用默认值")
                    score_config[key] = config["score"][key]
            
            # 验证output部分
            output_config = config["output"]
            if not isinstance(output_config["top_count"], int) or output_config["top_count"] <= 0:
                logger.warning(f"top_count应为正整数，当前值: {output_config['top_count']}，使用默认值10")
                output_config["top_count"] = 10
            
            if not isinstance(output_config["output_dir"], str) or not output_config["output_dir"]:
                logger.warning(f"output_dir应为非空字符串，当前值: {output_config['output_dir']}，使用默认值'output'")
                output_config["output_dir"] = "output"
            
            if not isinstance(output_config["auto_open_excel"], bool):
                logger.warning(f"auto_open_excel应为布尔值，当前值: {output_config['auto_open_excel']}，使用默认值True")
                output_config["auto_open_excel"] = True
            
        except Exception as e:
            logger.error(f"验证配置时出错: {e}")
            # 出错时不进行任何修改，保留原配置
    
    def get_market_data(self):
        """获取市场行情数据"""
        try:
            params = {
                'pn': 1,  # 页码
                'pz': 5000,  # 每页数量
                'po': 1,  # 排序方向，1表示升序
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,  # 数据精度
                'invt': 2,
                'fid': 'f3',  # 排序字段，f3表示涨跌幅
                'fs': 'm:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048',  # 沪深A股
                'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152',
                '_': int(time.time() * 1000),
            }
            
            logger.info("正在获取市场数据...")
            response = requests.get(self.stock_api, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = json.loads(response.text)
            if data['data'] is None:
                logger.error(f"API返回错误: {data}")
                return None
                
            return data['data']['diff']
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None
    
    def calculate_continuous_limit_up(self, stock_code):
        """计算股票连续涨停天数(模拟实现,实际应通过历史数据API)"""
        # 此处为示例实现,真实场景下应该调用历史数据API获取
        return 1
    
    def filter_stocks(self, stock_list):
        """筛选涨停股票"""
        if not stock_list:
            logger.error("没有输入股票数据")
            return []
        
        logger.info(f"开始筛选，原始股票数量: {len(stock_list)}")
        
        # 获取配置并进行安全检查
        config = self.config["filter"]
        
        # 安全获取配置项，如果出错使用默认值
        try:
            max_price = float(config.get("max_price", 40))
            min_limit_up_percent = float(config.get("min_limit_up_percent", 9.5))
            exclude_st = bool(config.get("exclude_st", True))
            exclude_sci_tech_board = bool(config.get("exclude_sci_tech_board", True))
            stock_prefix = config.get("stock_prefix", ["0", "6"])
            
            # 确保stock_prefix是列表
            if not isinstance(stock_prefix, list):
                stock_prefix = ["0", "6"]
                logger.warning("stock_prefix不是列表，使用默认值['0', '6']")
            
            # 如果stock_prefix为空列表，使用默认值
            if len(stock_prefix) == 0:
                stock_prefix = ["0", "6"]
                logger.warning("stock_prefix为空列表，使用默认值['0', '6']")
                
        except Exception as e:
            logger.error(f"获取筛选配置时出错: {e}，使用默认值")
            max_price = 40
            min_limit_up_percent = 9.5
            exclude_st = True
            exclude_sci_tech_board = True
            stock_prefix = ["0", "6"]
        
        # 第一步：仅保留指定前缀的股票
        prefix_filtered = []
        for stock in stock_list:
            try:
                stock_code = stock.get('f12', '')
                if any(stock_code.startswith(prefix) for prefix in stock_prefix):
                    prefix_filtered.append(stock)
            except Exception as e:
                logger.warning(f"筛选股票前缀时出错, 股票: {stock.get('f12', 'unknown')}, 错误: {e}")
        
        # 第二步：排除ST股票
        non_st_stocks = prefix_filtered
        if exclude_st:
            non_st_stocks = []
            for stock in prefix_filtered:
                try:
                    stock_name = stock.get('f14', '')
                    if 'ST' not in stock_name:
                        non_st_stocks.append(stock)
                except Exception as e:
                    logger.warning(f"排除ST股票时出错, 股票: {stock.get('f12', 'unknown')}, 错误: {e}")
        
        # 第三步：排除科创板股票
        filtered_stocks = non_st_stocks
        if exclude_sci_tech_board:
            filtered_stocks = []
            for stock in non_st_stocks:
                try:
                    stock_code = stock.get('f12', '')
                    if not stock_code.startswith('688'):
                        filtered_stocks.append(stock)
                except Exception as e:
                    logger.warning(f"排除科创板股票时出错, 股票: {stock.get('f12', 'unknown')}, 错误: {e}")
        
        # 第四步：排除高价股
        low_price_stocks = []
        for stock in filtered_stocks:
            try:
                # 获取价格
                price_raw = stock.get('f2', 0)
                
                # 尝试转换价格
                try:
                    # 如果价格是字符串，转换为浮点数
                    if isinstance(price_raw, str):
                        price = float(price_raw.replace(',', ''))
                    else:
                        price = float(price_raw)
                    
                    # 根据价格范围判断是否需要转换
                    if price < 1:  # 如果价格非常小，可能需要乘以1000
                        price = price * 1000
                    elif price > 1000:  # 如果价格非常大，可能需要除以1000
                        price = price / 1000
                    
                    # 判断是否低于最高价格
                    if price <= max_price:
                        low_price_stocks.append(stock)
                except Exception as e:
                    logger.warning(f"处理股票价格时出错, 价格: {price_raw}, 错误: {e}")
            except Exception as e:
                logger.warning(f"筛选高价股时出错, 股票: {stock.get('f12', 'unknown')}, 错误: {e}")
        
        # 第五步：筛选涨停股票
        limit_up_stocks = []
        
        for stock in low_price_stocks:
            try:
                # 获取涨跌幅
                change_percent_raw = stock.get('f3', 0)
                
                # 尝试转换涨跌幅
                try:
                    # 如果是字符串，去除百分号
                    if isinstance(change_percent_raw, str):
                        change_percent = float(change_percent_raw.replace('%', ''))
                    else:
                        change_percent = float(change_percent_raw)
                    
                    # 判断是否涨停
                    if change_percent >= min_limit_up_percent:
                        limit_up_stocks.append(stock)
                except Exception as e:
                    logger.warning(f"处理涨跌幅时出错, 涨跌幅: {change_percent_raw}, 错误: {e}")
            except Exception as e:
                logger.warning(f"筛选涨停股票时出错, 股票: {stock.get('f12', 'unknown')}, 错误: {e}")
        
        # 输出筛选结果数量
        logger.info(f"筛选结果: 前缀筛选后:{len(prefix_filtered)}只, 排除ST后:{len(non_st_stocks)}只, "
                  f"排除科创板后:{len(filtered_stocks)}只, 排除高价股后:{len(low_price_stocks)}只, "
                  f"最终涨停股票:{len(limit_up_stocks)}只")
        
        return limit_up_stocks
    
    def score_stocks(self, stock_list):
        """给涨停股票评分"""
        if not stock_list:
            return []
        
        # 获取评分配置
        score_config = self.config["score"]
        base_score = score_config["base_score"]
        volume_ratio_weight = score_config["volume_ratio_weight"]
        turnover_rate_weight = score_config["turnover_rate_weight"]
        continuous_limit_up_weight = score_config["continuous_limit_up_weight"]
        amount_weight = score_config["amount_weight"]
        amount_max_score = score_config["amount_max_score"]
        
        scored_stocks = []
        for stock in stock_list:
            score = 0
            
            # 基础分数
            change_percent = float(stock.get('f3', 0))
            volume_ratio = float(stock.get('f10', 0))
            turnover_rate = float(stock.get('f8', 0))
            amount = float(stock.get('f6', 0)) / 100000000  # 转换为亿元
            market_cap = float(stock.get('f20', 0)) / 100000000  # 流通市值,亿元
            
            # 计算连板数(实际应通过历史行情获取)
            stock_code = stock.get('f12', '')
            continuous_limit_up = self.calculate_continuous_limit_up(stock_code)
            
            # 涨停股票评分逻辑
            # 1. 基础分值
            score += base_score  # 涨停基础分
            
            # 2. 成交量和换手率评分
            score += volume_ratio * volume_ratio_weight  # 量比加分
            score += turnover_rate * turnover_rate_weight  # 换手率加分
            
            # 3. 连板数加分
            score += continuous_limit_up * continuous_limit_up_weight
            
            # 4. 成交额加分
            score += min(amount * amount_weight, amount_max_score)  # 成交额加分，最多15分
            
            # 5. 流通市值适中加分(10-50亿)
            if 10 <= market_cap <= 50:
                score += 10
            elif 50 < market_cap <= 100:
                score += 5
            
            # 记录评分和推荐理由
            reason = []
            if volume_ratio > 1.5:
                reason.append(f"量比高({volume_ratio:.2f})")
            if turnover_rate > 3:
                reason.append(f"换手率高({turnover_rate:.2f}%)")
            if continuous_limit_up > 1:
                reason.append(f"连续涨停{continuous_limit_up}天")
            if 10 <= market_cap <= 50:
                reason.append(f"流通市值适中({market_cap:.2f}亿)")
            if amount > 5:
                reason.append(f"成交活跃({amount:.2f}亿)")
            
            stock['score'] = score
            stock['reason'] = "、".join(reason) if reason else "综合指标评分"
            stock['continuous_limit_up'] = continuous_limit_up
            
            scored_stocks.append(stock)
        
        # 按评分排序
        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        return scored_stocks
    
    def run(self):
        """运行选股程序"""
        try:
            start_time = time.time()
            
            logger.info("=" * 50)
            logger.info("开始涨停股票筛选")
            logger.info("=" * 50)
            
            # 创建输出目录
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                logger.info(f"创建输出目录: {self.output_dir}")
            
            # 获取市场数据
            stock_list = self.get_market_data()
            if not stock_list:
                logger.error("获取市场数据失败")
                return
            
            logger.info(f"API返回总股票数: {len(stock_list)}")
            
            # 筛选涨停股票
            limit_up_stocks = self.filter_stocks(stock_list)
            logger.info(f"筛选出{len(limit_up_stocks)}只涨停股票")
            
            if not limit_up_stocks:
                logger.warning("今日没有涨停股票")
                return
            
            # 评分并排序
            recommended_stocks = self.score_stocks(limit_up_stocks)
            
            # 取前N只股票作为推荐
            top_count = self.config["output"]["top_count"]
            top_stocks = recommended_stocks[:top_count]
            
            if not top_stocks:
                logger.warning("评分后没有推荐股票")
                return
            
            # 保存结果到Excel
            excel_file = self.save_to_excel(top_stocks)
            
            # 打印推荐结果
            logger.info(f"今日推荐涨停股票(Top {top_count}):")
            for idx, stock in enumerate(top_stocks, 1):
                logger.info(f"{idx}. {stock.get('f14', '')}({stock.get('f12', '')}): 评分{stock['score']:.2f}, 换手率{float(stock.get('f8', 0)):.2f}%, 理由: {stock['reason']}")
            
            end_time = time.time()
            logger.info(f"选股程序运行完成，耗时{end_time - start_time:.2f}秒")
            logger.info(f"结果已保存到Excel文件: {excel_file}")
            
            # 自动打开Excel文件
            if self.config["output"]["auto_open_excel"]:
                try:
                    # 确认文件存在
                    if not os.path.exists(excel_file):
                        logger.warning(f"找不到Excel文件: {excel_file}")
                        return
                    
                    # 尝试用系统默认方式打开
                    try:
                        logger.info("尝试使用系统默认方式打开Excel文件...")
                        os.startfile(excel_file)
                        logger.info("已自动打开Excel文件")
                        return
                    except AttributeError:
                        # os.startfile不是在所有平台上都可用
                        pass
                    except Exception as e:
                        logger.warning(f"无法使用默认方式打开Excel文件: {e}")
                    
                    # 尝试替代方法
                    import platform
                    import subprocess
                    
                    system = platform.system()
                    
                    if system == 'Darwin':  # macOS
                        subprocess.call(['open', excel_file])
                        logger.info("已使用'open'命令打开Excel文件")
                    elif system == 'Linux':
                        subprocess.call(['xdg-open', excel_file])
                        logger.info("已使用'xdg-open'命令打开Excel文件")
                    elif system == 'Windows':
                        # 使用subprocess代替os.startfile
                        subprocess.Popen(['start', '', excel_file], shell=True)
                        logger.info("已使用subprocess打开Excel文件")
                    else:
                        logger.warning(f"未知操作系统: {system}，无法自动打开Excel文件")
                        
                except Exception as e:
                    logger.warning(f"无法自动打开Excel文件: {e}")
                    logger.info(f"您可以手动打开Excel文件: {excel_file}")
            
        except Exception as e:
            logger.error(f"选股程序运行出错: {e}")
    
    def save_to_excel(self, stock_list):
        """保存结果到Excel文件"""
        if not stock_list:
            logger.warning("没有符合条件的股票，无需保存")
            return None
        
        try:
            # 提取需要的字段
            data = []
            for stock in stock_list:
                data.append({
                    '代码': stock.get('f12', ''),
                    '名称': stock.get('f14', ''),
                    '现价': stock.get('f2', 0),  
                    '涨跌幅(%)': stock.get('f3', 0),
                    '成交额(亿)': stock.get('f6', 0) / 100000000,
                    '换手率(%)': stock.get('f8', 0),
                    '量比': stock.get('f10', 0),
                    '流通市值(亿)': stock.get('f20', 0) / 100000000,
                    '市盈率': stock.get('f9', 0),
                    '连板数': stock.get('continuous_limit_up', 1),
                    '评分': stock.get('score', 0),
                    '推荐理由': stock.get('reason', '')
                })
            
            # 创建DataFrame
            df = pd.DataFrame(data)
            
            # 获取当前日期作为文件名
            today = datetime.now().strftime('%Y%m%d')
            
            # 确保输出目录存在
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
            
            # 创建完整的文件路径（使用绝对路径）
            file_name = os.path.join(os.path.abspath(self.output_dir), f"涨停优选股_{today}.xlsx")
            
            # 保存到Excel
            df.to_excel(file_name, index=False)
            logger.info(f"推荐结果已保存到: {file_name}")
            return file_name
            
        except Exception as e:
            logger.error(f"保存Excel文件出错: {e}")
            return None

if __name__ == "__main__":
    selector = ZTSelector()
    selector.run()
