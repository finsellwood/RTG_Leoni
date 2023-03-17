import matplotlib.pylab as pl
import pandas as pd 
import numpy as np
ALPHA = 0.2 

def calc_ewma(data, alpha):
    running_output = []
    ewma = data[0]
    for a in range(len(data)):
        ewma = (alpha * data[a]) + (1-alpha) * ewma 
        running_output.append(ewma)
    return running_output



data_etf=pd.read_csv('etf_data.txt', sep=',', names=["time", 'midpoint prices'] )
data_fut=pd.read_csv('future_data.txt', sep=',', names=["time", 'midpoint prices'] )
data_etf = data_etf.tail(-100)
data_fut = data_fut.tail(-100)
ewma_future = calc_ewma(data_fut['midpoint prices'].to_numpy(), ALPHA)
# print(ewma_future)
future_gradient = np.gradient(data_fut['midpoint prices'], data_fut['time'])

# data_etf_sale=pd.read_csv('etf_sale_data.txt', sep=',', names=["time", 'midpoint prices'] )
# data_fut_sale=pd.read_csv('future_sale_data.txt', sep=',', names=["time", 'midpoint prices'] )
# data_etf_sale = data_etf_sale
# data_fut_sale = data_fut_sale


fig, ax = pl.subplots(2,1, sharex = True)

# pl.plot(data_etf['time'], data_etf['midpoint prices'], label = 'etf')
ax[0].plot(data_fut['time'], data_fut['midpoint prices'], label = 'future')
ax[1].plot(data_fut['time'], future_gradient, label = 'Gradient')
ax[1].plot(data_fut['time'], calc_ewma(future_gradient, 0.05), label = 'EWMA, a = 0.05')

ax[1].plot(data_fut['time'], calc_ewma(future_gradient, ALPHA), label = 'EWMA, a = 0.2')
ax[1].plot(data_fut['time'], calc_ewma(future_gradient, 0.5), label = 'EWMA, a = 0.5')
ax[1].plot(data_fut['time'], calc_ewma(future_gradient, 0.9), label = 'EWMA, a = 0.9')



# pl.plot(data_fut['time'], ewma_future, label = 'ewma')

# pl.plot(data_etf_sale['time'], data_etf_sale['midpoint prices'], label = 'etf sold prices')
# pl.plot(data_fut_sale['time'], data_fut_sale['midpoint prices'], label = 'future sold prices')
ax[1].legend()
pl.show()