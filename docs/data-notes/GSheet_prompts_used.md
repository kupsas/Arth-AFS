#TXN_TYPE

=AI(
"Classify the following bank transaction description into exactly ONE of the allowed transaction types below.

Allowed transaction types:
BANK_TRANSFER
UPI_EXPENSE
UPI_TRANSFER
CARD_EXPENSE
CARD_PAYMENT
INVESTMENT_BUY
INVESTMENT_SELL
LOAN_INSURANCE_PAYMENT
INCOME_OTHER
EXPENSE_OTHER

Rules:
- If it contains 'NEFT' or 'IMPS' it is a bank transfer → use BANK_TRANSFER
- If it starts with UPI and refers to a merchant → UPI_EXPENSE
- If it starts with UPI and refers to a person → UPI_TRANSFER
- If it mentions IB BILLPAY or credit card payment → CARD_PAYMENT
- If it mentions any part of my name (SASHANK SAI KUPPA) or 'MEICICI' in the description → SELF_TRANSFER (even if it is a bank/UPI transfer it will count as a SELF_TRANSFER)
- If it mentions ACH → LOAN_INSURANCE_PAYMENT
- If unclear, choose INCOME_OTHER (if income) or EXPENSE_OTHER (if expense)

Return ONLY the transaction type, nothing else.", O2)

#CHANNEL

=AI(
"Identify the transaction channel from the description below.

Rules:
- If it contains UPI → UPI
- If it contains UPI-LITE → UPI-LITE
- If it mentions IB BILLPAY, NEFT, IMPS, ACH, RDA → BANK
- If it refers to a credit card swipe → CARD
- If it refers to a stock broker or trading platform → BROKER

Return ONLY one of these values:
UPI
UPI-LITE
BANK
CARD
BROKER", O8)

#UPI_TYPE

=AI(
"Determine the UPI transaction type from the description below.

Rules:
- If the transaction is UPI and involves a business, merchant, brand, or service → P2M
- If the transaction is UPI and involves an individual person's name or phone number → P2P
- If the transaction is UPI-LITE → LITE_SELF_FUND
- If the transaction is NOT UPI → NA

Return ONLY one of these values:
P2P
P2M
LITE_SELF_FUND
NA", O6)

#COUNTERPARTY

=AI(
"You are an expert at normalizing financial transaction counterparties from Indian bank and UPI statements.

Your task:
Given ONE transaction description string, extract the most appropriate canonical counterparty name.

Rules:
- Group different payment processors under the same merchant (Razorpay, PayU, Cashfree, Paytm, etc.).
- Normalize brand variants (AMAZON RETAIL, AMAZON PAY → Amazon; Swiggy, Swiggy Instamart, Instamart, Dineout → Swiggy; etc.).
- Ignore reference numbers, transaction IDs, bank codes, and location suffixes.
- Prefer the most recognizable consumer-facing brand.
- If it is a person-to-person transfer, return the person's name.
- If it is a bank or financial institution, return the bank name.
- Return a short, clean name (2–4 words max).
- Do NOT include payment processor names.
- Do NOT include words like UPI, NEFT, IMPS, BANK, PAYMENT.

Examples:

Input:
UPI-AMAZON INDIA-AMAZON@RAPL-503322666760-YOU ARE PAYING FOR
Output:
Amazon

Input:
UPI-THIRD WAVE COFFEE-THIRDWAVECOFFEE.42605934@HDFCBANK-504311834904-UPI
Output:
Third Wave Coffee

Input:
UPI-RATHLAVATH RATHANKUM-9951272059@YBL-CNRB0000000-503288948740-UPI
Output:
Rathankum Rathlavath

Input:
UPI-GOOGLE INDIA DIGITAL-PLAYSTORE-GAMES@AXISBANK-503596672497-UPI
Output:
Google Play

Input:
IB BILLPAY DR-HDFC97-361010XXXX5778
Output:
HDFC Credit Card

Input:
NEFT DR-ICIC0001390-MEICICI-NETBANK, MUM
Output:
ICICI Bank

Input:
ACH D- POLICYBAZAAR-PBSI28045273
Output:
Policybazaar

Input:
IMPS-505814854755-SASHANK SAI KUPPA-ICIC
Output:
Sashank Sai Kuppa

Now extract the counterparty for the following transaction description.

Return ONLY the counterparty name. No explanation.

Transaction description:
", O6)

#COUNTERPARTY_CATEGORY

=AI(
"You are an expert at categorizing financial transaction counterparties into meaningful personal-finance categories.

Your task:
Given ONE sentence which contains both txn_type and counterparty name, assign EXACTLY ONE category from the list below.

Allowed categories and rules (all of them are case-insensitive):
- Salary & Income -> Only if the sentence contains SALARY
- Self Transfer -> Only if the sentence contains SELF_TRANSFER
- Rent & Housing -> Only if the sentence contains RENT_PAYMENT
- Utilities & Internet -> If it is a telecom, internet, water, electricity or gas bill payment
- Mobile, OTT & Subscriptions -> If it seems like a part of a recurring payment
- Swiggy -> If the sentence contains 'Swiggy'
- Food & Dining -> If the sentence contains a restaurant's name OR it contains 'Dineout'
- Travel & Stay -> If the sentence is related to hotels or air, train and bus travel
- Transport & Fuel -> If the sentence is related to a fuel station OR contains 'UBER'
- Healthcare & Pharmacy -> If the sentence is related to payments made at a hospital or a pharmacy
- Shopping & E-commerce -> If the sentence contains popular Indian e-commerce sites like Amazon, Flipkart, etc.
- Entertainment & Events -> If the sentence contains references to movies, concerts, malls etc. or popular ticketing platforms like BookMyShow, District, etc.
- Financial Services, Insurance & Banking -> If the sentence contains CARD_PAYMENT or LOAN_INSURANCE_PAYMENT
- Gifts & Personal Transfers -> If the sentence contains UPI_TRANSFER
- Fees, Charges & Interest -> If the sentence pertains to the fees, charges or interest related to other transactions
- Miscellaneous -> If none of the categories make sense then use this as a final resort

Examples:

Input: UPI_EXPENSE Nexus Shantiniketan  
Output: Entertainment & Events

Input: UPI_EXPENSE Amazon  
Output: Shopping & E-commerce

Input: UPI_EXPENSE Swiggy  
Output: Swiggy

Input: UPI_EXPENSE Swiggy Dineout 
Output: Food & Dining 

Input: UPI_EXPENSE Third Wave Coffee  
Output: Food & Dining

Input: UPI_EXPENSE Spotify  
Output: Mobile, OTT & Subscriptions

Input: UPI_EXPENSE JioFiber Prepaid  
Output: Utilities & Internet

Input: UPI_EXPENSE JioCinema  
Output: Mobile, OTT & Subscriptions

Input: UPI_EXPENSE Google Play  
Output: Mobile, OTT & Subscriptions

Input: UPI_EXPENSE Cleartrip  
Output: Travel & Stay

Input: UPI_EXPENSE Airbnb  
Output: Travel & Stay

Input: UPI_EXPENSE Uber  
Output: Transport & Fuel

Input: UPI_EXPENSE Samahita Fuelling Station  
Output: Transport & Fuel

Input: UPI_EXPENSE Apollo Pharmacy  
Output: Healthcare & Pharmacy

Input: UPI_EXPENSE Apollo 24|7  
Output: Healthcare & Pharmacy

Input: LOAN_INSURANCE_PAYMENT Policybazaar  
Output: Insurance

Input: LOAN_INSURANCE_PAYMENT HDFC Credit Card  
Output: Financial Services & Banking

Input: LOAN_INSURANCE_PAYMENT IDFC
Output: Financial Services & Banking

Input: BANK_TRANSFER Interest Paid  
Output: Fees, Charges & Interest

Input: EXPENSE_OTHER Sterling Rent  
Output: Rent & Housing

Input: UPI_EXPENSE Hotel Sarovar  
Output: Travel & Stay

Input: UPI_EXPENSE Ed Sheeran Concert  
Output: Entertainment & Events

Input: BANK_TRANSFER Sashank Sai Kuppa  
Output: Self Transfer

Return ONLY the category name. No explanation.
", L6)

