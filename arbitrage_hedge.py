# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import itertools

from typing import List

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side


LOT_SIZE = 30
LOT_SIZE_ARB = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
TICK_INTERVAL = 0.25
QUEUE_LENGTH = 600
HEDGE_DELAY = 10
SMALL_AVERAGE_LENGTH = 50
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS


class AutoTrader(BaseAutoTrader):
    """Example Auto-trader.

    When it starts this auto-trader places ten-lot bid and ask orders at the
    current best-bid and best-ask prices respectively. Thereafter, if it has
    a long position (it has bought more lots than it has sold) it reduces its
    bid and ask prices. Conversely, if it has a short position (it has sold
    more lots than it has bought) then it increases its bid and ask prices.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.best_ask_trade = 0
        self.best_bid_trade = 0
        self.arb_ticker = self.last_arb_time = 0
        self.time = 0
        self.bid_id_arb = self.ask_id_arb = 0
        self.last_bid_fut = self.last_ask_fut = 0
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.mid_prices = list([0]*SMALL_AVERAGE_LENGTH)
        self.time_passed  = itertools.count(1)
        self.current_time = 0

        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = self.best_ask = self.best_bid = 0

        # trend variables
        self.short_term_grad = self.med_term_grad = self.long_term_grad = self.ewma = 0
        self.hedge_delay = 0 # +1 for delay buy hedges, -1 for delay ask hedges

        # order queue variables
        self.queue_length = QUEUE_LENGTH
        self.id_order_queue = [0] * self.queue_length #stores ids of orders
        self.vol_order_queue = [0] * self.queue_length # stores volume of orders to be executed
        self.side_order_queue = [0] * self.queue_length # stores buy/ask side of orders to be execd
        self.time_order_queue = [0] * self.queue_length # stores the time for orders to be execd
        self.price_order_queue = [0] * self.queue_length # stores the price of orders to be execd

        self.queue_head = self.queue_tail = 0

        # debug variables
        self.no_bid_delayed = self.no_ask_delayed = 0

    def delay_hedge_order(self, execution_time:int, order_id:int, buy_or_ask:bool, order_price:int, order_vol:int):
        # true == buy, false == ask
        # push an order to a queue of orders, to be executed at a given counter value (execution time)
        self.queue_tail = (self.queue_tail + 1) % self.queue_length
        self.id_order_queue[self.queue_tail] = order_id
        self.vol_order_queue[self.queue_tail] = order_vol
        self.side_order_queue[self.queue_tail] = buy_or_ask
        self.price_order_queue[self.queue_tail] = order_price
        self.time_order_queue[self.queue_tail] = execution_time
    

    def pop_order(self):
        self.queue_head = (self.queue_head + 1) % self.queue_length
        return [self.time_order_queue[self.queue_head], self.id_order_queue[self.queue_head], self.side_order_queue[self.queue_head], \
                self.price_order_queue[self.queue_head], self.vol_order_queue[self.queue_head]]

    def peek_order(self):

        # returns the execution time of the next order in the queue
        # return [self.time_order_queue[self.queue_head], self.id_order_queue[self.queue_head], self.side_order_queue[self.queue_head], self.vol_order_queue[self.queue_head]]
        return self.time_order_queue[self.queue_head]
  
    def check_empty_hedge_queue(self):
        return self.queue_head == self.queue_tail
    
    def change_detect_simple(self):
        if self.short_term_grad > 50:
            self.hedge_delay = -1
            # print('autotrader_hedge_3 hedge delay -1')
        elif self.short_term_grad < -50:
            self.hedge_delay = +1
            # print('autotrader_hedge_3 hedge delay +1')

        else:
            self.hedge_delay = 0
            # print('autotrader_hedge_3 no hedge delay')


    def change_detect_ewma(self):
        print('ewma is', self.ewma)
        if self.ewma >= EWMA_THRESHOLD:
            # print('POSITIVE TREND')
            self.hedge_delay = -1
            # if trend is positive, want to delay any ASK hedge orders
        elif self.ewma <= (-1) * EWMA_THRESHOLD:
            # print('NEGATIVE TREND')
            self.hedge_delay = +1
        else:
            self.hedge_delay = 0
            # with no trend, execute all hedge orders on time   
        return

    def change_detect_inc_med(self):
        if self.short_term_grad >= 50 and self.short_term_grad > self.med_term_grad:
            # print('POSITIVE TREND')
            self.hedge_delay = -1
            # if trend is positive, want to delay any ASK hedge orders
        elif self.short_term_grad <= -50 and self.short_term_grad < self.med_term_grad:
            # print('NEGATIVE TREND')
            self.hedge_delay = +1
        else:
            self.hedge_delay = 0
            # with no trend, execute all hedge orders on time

    def change_detect_relative(self):
        if self.short_term_grad > 0 and self.short_term_grad > self.med_term_grad:
            # print('POSITIVE TREND')
            self.hedge_delay = -1
            # if trend is positive, want to delay any ASK hedge orders
        elif self.short_term_grad < 0 and self.short_term_grad < self.med_term_grad:
            # print('NEGATIVE TREND')
            self.hedge_delay = +1
        else:
            self.hedge_delay = 0
            # with no trend, execute all hedge orders on time  
    def trend_spotter(self):
        # try and notice positive or negative trend (currently using futures data)
        self.short_term_grad = (self.mid_prices[-1] - self.mid_prices[-SMALL_AVERAGE_LENGTH]) / (SMALL_AVERAGE_LENGTH*TICK_INTERVAL)
            # if len(self.mid_prices) >=100:
            #     self.long_term_grad = (self.mid_prices[-1] - self.mid_prices[-100]) / (5*TICK_INTERVAL)
        self.change_detect_simple()
        # self.change_detect_ewma()
        # print(self.short_term_grad)

    def calc_midpoints(self, bid_prices, ask_prices):
        if ask_prices[0] != 0:
            self.best_ask = ask_prices[0]
        if bid_prices[0] != 0:
            self.best_bid = bid_prices[0]

        middle = ((self.best_ask + self.best_bid)//2) # NOT A MULTIPLE OF TICK SIZE - used to see trends
        self.mid_prices.append(middle)

        self.trend_spotter()
    
    def data_log_midpoints(self, bid_prices, ask_prices, instrum):
        if ask_prices[0] != 0 and bid_prices[0] != 0:
            middle = ((ask_prices[0] + bid_prices[0])//2)
            time = self.current_time
            
                # only record every 10 datapoints (seem to get value every two ticks)
            # print(instrum)
            if instrum ==0:
                with open('future_data.txt', 'a') as g:
                    g.write('\n'+ str(time)+','+ str(middle))
                # print('writing to future data')
            if instrum ==1:
                with open('etf_data.txt', 'a') as f:
                    f.write('\n'+ str(time)+ ','+ str(middle))         
                # print('writing to etf data')

    def data_log_sold_midpoints(self, bid_prices, ask_prices, instrum):
        if ask_prices[0] != 0 and bid_prices[0] != 0:
            middle = ((ask_prices[0] + bid_prices[0])//2)
            time = self.current_time
            
                # only record every 10 datapoints (seem to get value every two ticks)
            # print(instrum ,'sale')
            if instrum ==0:
                with open('future_sale_data.txt', 'a') as g:
                    g.write('\n'+ str(time)+','+ str(middle))
                # print('writing to future data')
            if instrum ==1:
                with open('etf_sale_data.txt', 'a') as f:
                    f.write('\n'+ str(time)+ ','+ str(middle))         
                # print('writing to etf data')
    




    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received hedge filled for order %d with average price %d and volume %d", client_order_id,
                         price, volume)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        self.time += 1
        self.current_time = next(self.time_passed)

        self.data_log_midpoints(bid_prices, ask_prices, instrument)

        self.logger.info("received order book for instrument %d with sequence number %d", instrument,
                         sequence_number)
        """
        if len(self.bids) > 2:
            self.send_cancel_order(min(self.bids))
        if len(self.asks) > 2:
            self.send_cancel_order(min(self.asks))

        if (self.time - self.last_arb_time) > 3:  # not necessary if using FAK orders for arbitrage
            if self.bid_id_arb != 0:
                self.send_cancel_order(self.bid_id_arb)
                self.bid_id_arb = 0
            if self.ask_id_arb != 0:
                self.send_cancel_order(self.ask_id_arb)
                self.ask_id_arb = 0"""

        if instrument == Instrument.FUTURE:
            self.calc_midpoints(bid_prices, ask_prices)

            if bid_prices[0] != 0: self.last_bid_fut = bid_prices[0]
            if ask_prices[0] != 0: self.last_ask_fut = ask_prices[0]

            price_adjustment = - (self.position // LOT_SIZE) * TICK_SIZE_IN_CENTS
            mid = ((bid_prices[0] + ask_prices[0]) // 2) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
            spread = 6 * TICK_SIZE_IN_CENTS

            new_bid_price = mid - spread // 2 + price_adjustment if bid_prices[0] != 0 else 0
            new_ask_price = mid + spread // 2 + price_adjustment if ask_prices[0] != 0 else 0

            # essentially cancels previous order if new bid or ask are truly new
            if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
            if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0

            if self.bid_id == 0 and new_bid_price != 0 and self.position < 1.0*(POSITION_LIMIT-1.5*LOT_SIZE):
                self.arb_ticker = 0
                self.bid_id = next(self.order_ids)
                self.bid_price = new_bid_price
                self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.bid_id)

            if self.ask_id == 0 and new_ask_price != 0 and self.position > -1.0*(POSITION_LIMIT-1.5*LOT_SIZE):
                self.arb_ticker = 0
                self.ask_id = next(self.order_ids)
                self.ask_price = new_ask_price
                self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.ask_id)
        # EXECUTE QUEUED HEDGE ORDERS 
        # want to check for orders that have reached due time, and execute them
        next_order_exec_time = self.peek_order()
        if not self.check_empty_hedge_queue() and next_order_exec_time <= self.current_time:
            order_info = self.pop_order()
            self.send_hedge_order(next(self.order_ids), order_info[2], order_info[3], order_info[4])
            print('executed delayed hedge on side ', order_info[2], 'with volume', order_info[4], 'at time ', self.current_time)
            if order_info[2] == Side.ASK:
                self.no_ask_delayed -=1
            elif order_info[2] == Side.BID:
                self.no_bid_delayed -=1
            # print(order_info)
        if instrument == Instrument.ETF:
            delta_a = delta_b = 0
            # if bid of etf is higher or equal than fut ask decent change for arbitrage  => sell etf at bid_prices[0]
            if (self.last_ask_fut != 0) and (bid_prices[0] != 0): delta_a = (bid_prices[0] - self.last_ask_fut)//TICK_SIZE_IN_CENTS
            # if ask of etf is lower or equal than bid decent change for arbitrage => buy etf at ask_prices[0]
            if (self.last_bid_fut != 0) and (ask_prices[0] != 0): delta_b = (self.last_bid_fut - ask_prices[0])//TICK_SIZE_IN_CENTS

            # print(delta_a,delta_b)
            if delta_a > 2 and self.position > -0.8*POSITION_LIMIT and self.arb_ticker < 2:
                print("Ask delta: " +str(delta_a))
                self.arb_ticker += 1
                self.ask_id_arb = next(self.order_ids)
                price = (bid_prices[0] - 000) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
                print(price, self.last_ask_fut)
                self.send_insert_order(self.ask_id_arb, Side.SELL, price, LOT_SIZE_ARB, Lifespan.FILL_AND_KILL)
                self.asks.add(self.ask_id_arb)

            if delta_b > 2 and self.position < 0.8*POSITION_LIMIT and self.arb_ticker < 2:
                print("Bid delta: " + str(delta_b))
                self.arb_ticker += 1
                self.bid_id_arb = next(self.order_ids)
                price = (ask_prices[0] + 000)//TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
                print(price, self.last_bid_fut)
                self.send_insert_order(self.bid_id_arb, Side.BUY, price, LOT_SIZE_ARB, Lifespan.FILL_AND_KILL)
                self.bids.add(self.bid_id_arb)

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.bids:
            self.position += volume
            if self.hedge_delay == -1 and client_order_id != self.bid_id_arb:
                # delay the hedge
                self.delay_hedge_order(self.current_time+HEDGE_DELAY, 0 , Side.ASK, MIN_BID_NEAREST_TICK, volume)
                print('delayed ASK hedge order with volume', volume, 'at time ', self.current_time)
                self.no_ask_delayed +=1
            else:
                self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
            # print(MIN_BID_NEAREST_TICK, 'hedge - mbnt')
            if (client_order_id == self.bid_id_arb):
                print("bid arbitrage executed "+ str(self.time))
            if (client_order_id == self.bid_id_arb) and (volume < LOT_SIZE_ARB):
                self.send_cancel_order(self.bid_id_arb)

        elif client_order_id in self.asks:
            self.position -= volume
            if self.hedge_delay == +1 and client_order_id != self.ask_id_arb:
                # delay hedge, as it is a bid hedge
                self.delay_hedge_order(self.current_time+HEDGE_DELAY, 0 , Side.BID, MAX_ASK_NEAREST_TICK, volume)
                print('delayed BID hedge order with volume', volume, 'at time ', self.current_time)
                self.no_bid_delayed +=1
            else:
                self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)
            # print(MAX_ASK_NEAREST_TICK, 'hedge - mant')
        
            if (client_order_id == self.ask_id_arb):
                print("ask arbitrage executed " + str(self.time))
            if (client_order_id == self.ask_id_arb) and (volume < LOT_SIZE_ARB):
                self.send_cancel_order(self.ask_id_arb)

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
                         client_order_id, fill_volume, remaining_volume, fees)
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0

            # It could be either a bid or an ask
            self.bids.discard(client_order_id)
            self.asks.discard(client_order_id)

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the aggregated volume
        traded at each of those price levels.

        If there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes arrays.
        """
        if ask_prices[0] != 0:
            self.best_ask_trade = ask_prices[0]
        if bid_prices[0] != 0:
            self.best_bid_trade = bid_prices[0]

        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
                         sequence_number)