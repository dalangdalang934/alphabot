import os
import json
import time
import web3
import logging
from web3 import Web3
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

# Load environment variables
load_dotenv()

# Load ABIs from files
with open('./tokenabi.js', 'r') as file:
    TOKEN_ABI = json.loads(file.read())

with open('./swapabi.js', 'r') as file:
    PANCAKESWAP_ABI = json.loads(file.read())

# Configuration from environment variables
RPC_URL = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/') # BSC mainnet RPC
PRIVATE_KEY = os.getenv('PRIVATE_KEY') # Wallet B private key
TOKEN_ADDRESS = os.getenv('TOKEN_ADDRESS') # ERC20 token contract address
PANCAKESWAP_ROUTER_ADDRESS = os.getenv('PANCAKESWAP_ROUTER_ADDRESS', '0x10ED43C718714eb63d5aA57B78B54704E256024E') # PancakeSwap Router V2
WBNB_ADDRESS = os.getenv('WBNB_ADDRESS', '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c') # WBNB address
WALLET_A_ADDRESS = os.getenv('WALLET_A_ADDRESS') # Wallet A address
TOKEN_AMOUNT = os.getenv('TOKEN_AMOUNT', '100') # Amount to transfer (e.g., 100 tokens)
TOKEN_DECIMALS = int(os.getenv('TOKEN_DECIMALS', '18'))
DEADLINE_MINUTES = int(os.getenv('DEADLINE_MINUTES', '20'))
GAS_LIMIT_TRANSFER = int(os.getenv('GAS_LIMIT_TRANSFER', '100000'))
GAS_LIMIT_APPROVE = int(os.getenv('GAS_LIMIT_APPROVE', '100000'))
GAS_LIMIT_SWAP = int(os.getenv('GAS_LIMIT_SWAP', '300000'))

# 循环次数和间隔
LOOP_COUNT = int(os.getenv('LOOP_COUNT', '10'))  # 默认运行10次
LOOP_INTERVAL = int(os.getenv('LOOP_INTERVAL', '2'))  # 每次循环间隔秒数

# 批准设置
MAX_UINT256 = 2**256 - 1  # 无限批准金额

# Swap settings
SLIPPAGE = float(os.getenv('SLIPPAGE', '0.1')) # 滑点百分比，默认0.1%

# Validate required environment variables
required_env_vars = ['PRIVATE_KEY', 'TOKEN_ADDRESS', 'WALLET_A_ADDRESS']
for env_var in required_env_vars:
    if not os.getenv(env_var):
        print(f"Error: Environment variable {env_var} is required but not set.")
        print('Please create a .env file with the required variables or set them in your environment.')
        exit(1)

# Initialize Web3 and account
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Get wallet address from private key
wallet_b_address = w3.eth.account.from_key(PRIVATE_KEY).address

# Initialize contracts
token_contract = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_ADDRESS), abi=TOKEN_ABI)
router_contract = w3.eth.contract(address=Web3.to_checksum_address(PANCAKESWAP_ROUTER_ADDRESS), abi=PANCAKESWAP_ABI)

# Calculate the amount to transfer with proper decimals
AMOUNT_TO_TRANSFER = int(float(TOKEN_AMOUNT) * (10 ** TOKEN_DECIMALS))

# Calculate deadline timestamp
DEADLINE = int(time.time()) + (60 * DEADLINE_MINUTES)  # Default: 20 minutes from now

# 等待新区块函数
def wait_for_new_block(current_block):
    logging.info(f"等待新区块 | 当前区块: {current_block}")
    while True:
        latest_block = w3.eth.block_number
        if latest_block > current_block:
            logging.info(f"新区块: {latest_block} (在当前+{latest_block-current_block})")
            return latest_block
        time.sleep(0.5)  # 每0.5秒检查一次新区块

# 发送交易并重试直到成功
def send_transaction_with_retry(signed_tx, tx_type, max_attempts=999):
    attempt = 1
    while attempt <= max_attempts:
        try:
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_short = tx_hash.hex()[:10] + '...' # 只显示哈希前10位
            logging.info(f"{tx_type} 发送成功 | Hash: {tx_hash_short}")
            
            # 等待交易完成
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            logging.info(f"{tx_type} 确认 | 区块: {tx_receipt['blockNumber']} | 状态: {'成功' if tx_receipt['status'] == 1 else '失败'}")
            
            return tx_hash, tx_receipt
        except Exception as e:
            error_msg = str(e)
            # 提取简短错误信息
            if "already known" in error_msg:
                short_error = "交易已提交"
            elif "nonce too low" in error_msg:
                short_error = "nonce过低"
            else:
                # 限制错误消息长度
                short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
            
            logging.error(f"{tx_type} 失败 (尝试 {attempt}/{max_attempts}): {short_error}")
            
            if "already known" in error_msg or "nonce too low" in error_msg:
                try:
                    if 'tx_hash' in locals():
                        tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
                        if tx_receipt is not None:
                            logging.info(f"{tx_type} 已确认 | 区块: {tx_receipt['blockNumber']}")
                            return tx_hash, tx_receipt
                except:
                    pass
            
            # 等待新区块后重试
            current_block = w3.eth.block_number
            wait_for_new_block(current_block)
            attempt += 1
    
    raise Exception(f"{tx_type} 在 {max_attempts} 次尝试后失败")

# 执行transferFrom交易，每2秒发送一次直到成功
def execute_transfer_from():
    # 获取钱包A的转账前余额
    initial_a_balance = token_contract.functions.balanceOf(Web3.to_checksum_address(WALLET_A_ADDRESS)).call()
    logging.info(f"Transfer前钱包A余额: {initial_a_balance / (10 ** TOKEN_DECIMALS)}")
    
    # 设置开始时间
    start_time = time.time()
    
    # 初始化本地nonce计数器 - 解决nonce过低问题
    local_nonce = w3.eth.get_transaction_count(wallet_b_address)
    
    transfer_success = False
    while not transfer_success:
        try:
            # 计算自上次交易的时间
            elapsed = time.time() - start_time
            if elapsed < 2:
                # 如果距离上次交易不到2秒，等待剩余时间
                time.sleep(max(0, 2 - elapsed))
            
            # 重置开始时间为现在
            start_time = time.time()
            
            # 获取链上当前nonce和使用本地nonce的最大值
            chain_nonce = w3.eth.get_transaction_count(wallet_b_address)
            # 选择链上和本地计算的最大nonce值
            current_nonce = max(local_nonce, chain_nonce)
            logging.info(f"Transfer | nonce: {current_nonce} (链上: {chain_nonce})")
            
            # 构建transferFrom交易 - 从钱包A转到钱包B
            transfer_txn = token_contract.functions.transferFrom(
                Web3.to_checksum_address(WALLET_A_ADDRESS),
                wallet_b_address,  # 目标地址是B钱包地址
                AMOUNT_TO_TRANSFER
            ).build_transaction({
                'chainId': w3.eth.chain_id,
                'gas': GAS_LIMIT_TRANSFER,
                'gasPrice': w3.eth.gas_price,
                'nonce': current_nonce,
            })
            
            # 签名交易
            signed_txn = w3.eth.account.sign_transaction(transfer_txn, PRIVATE_KEY)
            
            try:
                # 发送交易并等待确认
                tx_hash, tx_receipt = send_transaction_with_retry(signed_txn, "Transfer")
                current_block = tx_receipt['blockNumber']
                
                # 交易成功，验证结果
                new_a_balance = token_contract.functions.balanceOf(Web3.to_checksum_address(WALLET_A_ADDRESS)).call()
                
                if tx_receipt['status'] == 1:  # 交易状态成功
                    logging.info(f"✅ Transfer成功 | 钱包A余额: {new_a_balance / (10 ** TOKEN_DECIMALS)}")
                    transfer_success = True
                    return True, current_block
                else:
                    # 交易状态失败但已发送到区块链，增加nonce
                    logging.error("❌ 状态失败，增加nonce并继续重试")
                    local_nonce = current_nonce + 1  # 增加本地nonce
            except Exception as e:
                error_msg = str(e)
                
                # 处理nonce过低错误
                if "nonce too low" in error_msg:
                    logging.warning(f"Nonce过低错误 | 当前nonce: {current_nonce}")
                    # 自动增加nonce继续尝试
                    local_nonce = current_nonce + 1
                    logging.info(f"自动增加nonce至: {local_nonce}")
                    continue  # 立即重试，不等待2秒
                    
                short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
                logging.error(f"Transfer失败: {short_error}")
        except Exception as e:
            error_msg = str(e)
            short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
            logging.error(f"Transfer外部错误: {short_error}")
            # 全局错误，但不增加nonce
    
    return False, None

# 执行swap操作
def execute_swap():
    """执行一次swap交易，将代币兑换为BNB并发送到钱包A地址"""
    # 检查代币余额
    try:
        token_balance = token_contract.functions.balanceOf(wallet_b_address).call()
        logging.info(f"当前代币余额: {token_balance / (10 ** TOKEN_DECIMALS)}")
        
        if token_balance < AMOUNT_TO_TRANSFER:
            logging.error(f"代币余额不足 | 需要: {AMOUNT_TO_TRANSFER / (10 ** TOKEN_DECIMALS)}, 实际: {token_balance / (10 ** TOKEN_DECIMALS)}")
            return False, None, None
    except Exception as e:
        logging.warning(f"检查代币余额失败: {str(e)[:30]}...")
        return False, None, None
    
    # 检查授权额度
    try:
        current_allowance = token_contract.functions.allowance(
            wallet_b_address,
            Web3.to_checksum_address(PANCAKESWAP_ROUTER_ADDRESS)
        ).call()
        logging.info(f"Swap前授权额度: {current_allowance / (10 ** TOKEN_DECIMALS)}")
        
        if current_allowance < AMOUNT_TO_TRANSFER:
            logging.info("尝试重新授权...")
            approve_success, _ = approve_token_with_max_amount()
            if not approve_success:
                return False, None, None
    except Exception as e:
        logging.warning(f"检查授权失败: {str(e)[:30]}...")
    
    # 获取交易前的余额
    token_balance_before = token_contract.functions.balanceOf(wallet_b_address).call()
    bnb_balance_before = w3.eth.get_balance(wallet_b_address)
    logging.info(f"开始交易 | 代币: {token_balance_before / (10 ** TOKEN_DECIMALS)} | BNB: {w3.from_wei(bnb_balance_before, 'ether')}")
    logging.info(f"使用滑点: {SLIPPAGE}%")
    
    try:
        # 准备swap相关参数
        path = [Web3.to_checksum_address(TOKEN_ADDRESS), Web3.to_checksum_address(WBNB_ADDRESS)]
        
        # 获取当前兑换比率
        try:
            amounts_out = router_contract.functions.getAmountsOut(
                AMOUNT_TO_TRANSFER, 
                path
            ).call()
            expected_amount = amounts_out[1]  # 第二个值是期望获得的BNB数量
            
            # 设置较大的滑点容忍度，增加成功率
            amount_out_min = int(expected_amount * 0.95)  # 允许5%的滑点
            logging.info(f"兑换估算 | 预期: {w3.from_wei(expected_amount, 'ether')} BNB | 最小: {w3.from_wei(amount_out_min, 'ether')} BNB")
        except Exception as e:
            logging.warning(f"计算滑点失败: {str(e)[:30]}...")
            amount_out_min = 0
        
        # 获取最新nonce
        current_nonce = w3.eth.get_transaction_count(wallet_b_address)
        logging.info(f"Swap | nonce: {current_nonce}")
        
        # 设置较高的gas价格和限额
        gas_price_boost = int(w3.eth.gas_price * 1.2)  # 增加20%
        gas_limit_boost = int(GAS_LIMIT_SWAP * 1.3)  # 增加30%
        
        # 构建交易
        swap_txn = router_contract.functions.swapExactTokensForETH(
            AMOUNT_TO_TRANSFER,
            amount_out_min,
            path,
            Web3.to_checksum_address(WALLET_A_ADDRESS),  # 接收BNB的地址是钱包A
            DEADLINE
        ).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': gas_limit_boost,
            'gasPrice': gas_price_boost,
            'nonce': current_nonce,
        })
        
        # 签名并发送交易
        signed_swap_txn = w3.eth.account.sign_transaction(swap_txn, PRIVATE_KEY)
        swap_tx_hash, swap_tx_receipt = send_transaction_with_retry(signed_swap_txn, "Swap")
        
        # 获取交易区块
        swap_block = swap_tx_receipt['blockNumber']
        
        # 验证交易效果
        token_balance_after = token_contract.functions.balanceOf(wallet_b_address).call()
        
        # 检查交易状态
        if swap_tx_receipt['status'] == 1:
            logging.info("✅ Swap交易状态成功")
            return True, None, swap_block
        else:
            # 即使状态是失败，如果代币已经减少，我们也认为交易完成
            if token_balance_after < token_balance_before:
                logging.info("✅ Swap可能成功 (代币已消耗)")
                return True, None, swap_block
            else:
                logging.error("❌ Swap交易失败")
                return False, None, None
            
    except Exception as e:
        error_msg = str(e)
        short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
        logging.error(f"Swap执行错误: {short_error}")
        return False, None, None
    return False, None, None

# 无限批准函数
def approve_token_with_max_amount():
    logging.info("开始无限批准代币...")
    
    try:
        # 获取当前nonce
        current_nonce = w3.eth.get_transaction_count(wallet_b_address)
        
        # 构建approve交易，使用无限大的数字
        approve_txn = token_contract.functions.approve(
            Web3.to_checksum_address(PANCAKESWAP_ROUTER_ADDRESS),
            MAX_UINT256  # 无限批准
        ).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': GAS_LIMIT_APPROVE,
            'gasPrice': w3.eth.gas_price,
            'nonce': current_nonce,
        })
        
        # 签名并发送交易
        signed_txn = w3.eth.account.sign_transaction(approve_txn, PRIVATE_KEY)
        tx_hash, tx_receipt = send_transaction_with_retry(signed_txn, "无限批准")
        
        # 检查是否成功
        if tx_receipt['status'] == 1:
            # 检查授权额度
            allowance = token_contract.functions.allowance(
                wallet_b_address,
                Web3.to_checksum_address(PANCAKESWAP_ROUTER_ADDRESS)
            ).call()
            
            if allowance == MAX_UINT256:
                logging.info(f"✅ 无限批准成功 | 授权额度: 无限大")
                return True
            else:
                logging.info(f"✅ 批准成功 | 授权额度: {allowance}")
                return True
        else:
            logging.error("❌ 无限批准失败")
            return False
    except Exception as e:
        error_msg = str(e)
        short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
        logging.error(f"无限批准错误: {short_error}")
        return False

# 撤销批准函数
def revoke_token_approval():
    logging.info("开始撤销代币批准...")
    
    try:
        # 获取当前nonce
        current_nonce = w3.eth.get_transaction_count(wallet_b_address)
        
        # 构建撤销approve交易，将授权额度设为0
        revoke_txn = token_contract.functions.approve(
            Web3.to_checksum_address(PANCAKESWAP_ROUTER_ADDRESS),
            0  # 将授权额度设为0来撤销
        ).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': GAS_LIMIT_APPROVE,
            'gasPrice': w3.eth.gas_price,
            'nonce': current_nonce,
        })
        
        # 签名并发送交易
        signed_txn = w3.eth.account.sign_transaction(revoke_txn, PRIVATE_KEY)
        tx_hash, tx_receipt = send_transaction_with_retry(signed_txn, "撤销批准")
        
        # 检查是否成功
        if tx_receipt['status'] == 1:
            logging.info("✅ 撤销批准成功")
            return True
        else:
            logging.error("❌ 撤销批准失败")
            return False
    except Exception as e:
        error_msg = str(e)
        short_error = error_msg[:50] + '...' if len(error_msg) > 50 else error_msg
        logging.error(f"撤销批准错误: {short_error}")
        return False

def main():
    try:
        logging.info(f"钱包地址: {wallet_b_address}")
        
        # 获取初始nonce
        initial_nonce = w3.eth.get_transaction_count(wallet_b_address)
        logging.info(f"初始nonce: {initial_nonce}")
        
        # 先进行无限批准
        if not approve_token_with_max_amount():
            logging.error("无限批准失败，无法继续")
            return
        
        # 循环执行指定次数
        loop_counter = 1
        while loop_counter <= LOOP_COUNT:
            logging.info(f"\n===== 开始第 {loop_counter}/{LOOP_COUNT} 次循环 =====\n")
            
            # 执行transferFrom交易，每2秒一次直到成功
            logging.info("开始执行transferFrom交易，每2秒发送一次直到成功")
            
            # 执行transferFrom直到成功
            success, block = execute_transfer_from()
            if not success:
                logging.error(f"循环 {loop_counter}: 无法完成transferFrom交易")
                loop_counter += 1
                if loop_counter <= LOOP_COUNT:
                    logging.info(f"等待 {LOOP_INTERVAL} 秒后尝试下一次循环...")
                    time.sleep(LOOP_INTERVAL)
                continue
            
            logging.info(f"✨ 循环 {loop_counter}: TransferFrom成功完成！开始执行swap")
            
            # 等待短暂停后继续下一步操作
            time.sleep(0.1)
            
            # 执行swap操作（使用无限批准）
            success, _, swap_block = execute_swap()
            if not success:
                logging.error(f"循环 {loop_counter}: 无法完成swap交易")
            else:
                logging.info(f"✨ 循环 {loop_counter}: Swap成功完成!")
                
            # 增加循环计数并等待指定时间
            loop_counter += 1
            if loop_counter <= LOOP_COUNT:
                logging.info(f"等待 {LOOP_INTERVAL} 秒后开始下一次循环...")
                time.sleep(LOOP_INTERVAL)
        
        # 全部完成后撤销批准
        logging.info("\n===== 全部循环完成，开始撤销批准 =====\n")
        if revoke_token_approval():
            logging.info("✨✨✨ 所有操作已成功完成，并已撤销批准! ✨✨✨")
        else:
            logging.warning("✨✨✨ 循环操作完成，但撤销批准失败! ✨✨✨")
    except Exception as error:
        error_msg = str(error)
        short_error = error_msg[:100] + '...' if len(error_msg) > 100 else error_msg
        logging.error(f"错误: {short_error}")
        # 如果出错，尝试撤销批准
        logging.info("出错，尝试撤销批准...")
        revoke_token_approval()
        raise
        
        # 获取swap前的代币余额和BNB余额
        token_balance_before = token_contract.functions.balanceOf(wallet_b_address).call()
        bnb_balance_before = w3.eth.get_balance(wallet_b_address)
        logging.info(f"Swap前代币余额: {token_balance_before / (10 ** TOKEN_DECIMALS)}")
        logging.info(f"Swap剋BNB余额: {w3.from_wei(bnb_balance_before, 'ether')} ETH")
        
        swap_success = False
        while not swap_success:
            try:
                # 重新获取当前nonce
                current_nonce = w3.eth.get_transaction_count(wallet_b_address)
                logging.info(f"Swap使用nonce: {current_nonce}")
                
                # 构建swap交易
                swap_txn = router_contract.functions.swapExactTokensForETH(
                    AMOUNT_TO_TRANSFER,
                    amount_out_min,
                    path,
                    Web3.to_checksum_address(WALLET_A_ADDRESS),
                    DEADLINE
                ).build_transaction({
                    'chainId': w3.eth.chain_id,
                    'gas': GAS_LIMIT_SWAP,
                    'gasPrice': w3.eth.gas_price,
                    'nonce': current_nonce,
                })
                
                # 签名交易
                signed_txn = w3.eth.account.sign_transaction(swap_txn, PRIVATE_KEY)
                
                # 发送交易并等待确认
                tx_hash, tx_receipt = send_transaction_with_retry(signed_txn, "Swap")
                
                # 获取当前区块
                current_block = tx_receipt['blockNumber']
                logging.info(f"Swap 交易已在区块 {current_block} 确认")
                
                # 即时验证swap是否真正生效 - 检查代币减少和BNB增加
                token_balance_after = token_contract.functions.balanceOf(wallet_b_address).call()
                bnb_balance_after = w3.eth.get_balance(wallet_b_address)
                
                logging.info(f"Swap后代币余额: {token_balance_after / (10 ** TOKEN_DECIMALS)}")
                logging.info(f"Swap后BNB余额: {w3.from_wei(bnb_balance_after, 'ether')} ETH")
                
                # 检查代币是否减少和BNB是否增加
                token_decreased = token_balance_after < token_balance_before
                bnb_increased = bnb_balance_after > bnb_balance_before
                
                if token_decreased and bnb_increased:
                    logging.info("✅ Swap交互成功确认：代币已减少，BNB已增加")
                    swap_success = True
                elif token_decreased:
                    logging.warning("⚠️ 代币已减少但BNB未增加，可能是手续费过高")
                    if tx_receipt['status'] == 1:  # 交易状态成功
                        logging.info("交易状态成功，将视为成功完成")
                        swap_success = True
                elif bnb_increased:
                    logging.warning("⚠️ BNB已增加但代币未减少，这是意外情况")
                    if tx_receipt['status'] == 1:  # 交易状态成功
                        logging.info("交易状态成功，将视为成功完成")
                        swap_success = True
                else:
                    # 交易确认但没有实际变化
                    if tx_receipt['status'] == 1:  # 交易状态成功
                        logging.warning("⚠️ 交易状态成功但余额未变化，可能需要检查交易参数")
                        # 可能由于交易路径或参数问题导致实际没有交换成功
                        # 如果你确定这种情况属于正常，可以取消下面的注释
                        # swap_success = True
                    else:
                        logging.error("❌ 交易状态失败，将重试...")
                
                if not swap_success:
                    time.sleep(0.5)  # 等待后重试
            except Exception as e:
                error_str = str(e)
                logging.error(f"Swap执行失败: {error_str}")
                
                # 特殊处理TransferHelper: TRANSFER_FROM_FAILED错误
                if "TRANSFER_FROM_FAILED" in error_str:
                    logging.warning("检测到TRANSFER_FROM_FAILED错误，可能是代币合约限制或授权问题")
                    
                    # 检查代币是否有一次性购买费用或其他特殊限制
                    try:
                        # 重新完全授权
                        logging.info("尝试重新完全授权...")
                        approve_success, _ = approve_token_with_max_amount()
                        if approve_success:
                            logging.info("重新授权成功，等待一秒后继续...")
                            time.sleep(1)  # 等待更长时间让区块链处理授权
                            continue
                    except Exception as approve_error:
                        logging.error(f"重新授权失败: {str(approve_error)}")
                
                # 尝试调整金额
                if "TRANSFER_FROM_FAILED" in error_str and AMOUNT_TO_TRANSFER > 1:
                    reduced_amount = int(AMOUNT_TO_TRANSFER * 0.9)  # 减少10%
                    logging.info(f"尝试降低交易金额至: {reduced_amount / (10 ** TOKEN_DECIMALS)}")
                    # 不实际修改全局AMOUNT_TO_TRANSFER变量，只在这次尝试中使用较低的金额
                    AMOUNT_TO_TRANSFER = reduced_amount
                    time.sleep(1)
                    continue
                    
                logging.info("等待1秒后重试...")
                time.sleep(1)  # 增加等待时间
        
        logging.info("所有操作已成功完成!")
    except Exception as error:
        logging.error(f"错误: {error}")
        raise

# Run the script
if __name__ == "__main__":
    main()