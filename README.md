# BSC 交易自动化工具

## 🔖 项目概述

本工具是一个用于在币安智能链（BSC）上执行自动化交易操作的脚本。该工具仅用于**研究与教育目的**，旨在帮助用户了解区块链交易机制和智能合约交互原理。

## ⚠️ 免责声明

**重要提示：使用本工具前，请仔细阅读以下免责声明**

1. **教育目的**：本工具仅供研究和教育目的使用。用户应自行负责确保其使用符合当地法律法规。

2. **非投资建议**：本工具不提供任何投资建议。使用本工具进行的任何交易决策均由用户自行承担责任。

3. **风险提示**：加密货币交易存在高风险，包括但不限于市场波动、流动性风险、技术风险等。用户应在充分了解风险的前提下使用本工具。

4. **责任限制**：开发者不对因使用本工具而导致的任何直接或间接损失承担责任，包括但不限于资金损失、数据丢失或业务中断。

5. **非附属关系**：本工具与币安、PancakeSwap或任何其他提及的平台或服务均无官方附属关系。

6. **法律合规**：用户有责任确保其使用本工具的方式符合其所在司法管辖区的所有适用法律法规，包括但不限于证券法、税法和反洗钱法规。

## 🔒 安全提示

1. **私钥安全**：永远不要将您的私钥分享给任何人。本工具需要使用私钥进行交易签名，请确保在安全的环境中使用。

2. **环境变量**：将敏感信息（如私钥）存储在.env文件中，并确保该文件不会被提交到代码仓库。

3. **测试小额**：首次使用时，建议使用小额资金测试功能，确认一切正常后再考虑使用更大金额。

## 🛠️ 使用说明

1. 安装必要的依赖：
   ```
   pip install -r requirements.txt
   ```

2. 配置.env文件：
   - 设置RPC_URL（BSC节点URL）
   - 设置PRIVATE_KEY（钱包私钥，带0x前缀）
   - 设置合约地址和其他参数

3. 运行脚本：
   ```
   python tas.py
   ```

## 📝 注意事项

- 本工具不保证交易一定成功或能获取预期收益
- 使用前请确保了解BSC网络和智能合约的基本原理
- 请勿用于任何可能违反法律、法规或第三方服务条款的活动

## ⚖️ 法律风险提示

加密货币的法律地位在全球各地区存在差异。在使用本工具前，请咨询专业法律顾问，了解您所在地区关于加密货币交易的法律规定。

---

**使用本工具即表示您已阅读并同意上述免责声明和条款。如不同意，请勿使用本工具。**

最后更新：2025年5月28日
