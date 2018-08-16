from ocs import ocs_agent
#import op_model as opm

import time, threading

class Subscriber:
    def __init__(self, agent, feed):
        self.agent = agent
        self.feed = feed
        
    def handler(self, data):
        channel = data["channel"]
        print ("Message from %s: "%self.feed, channel)
        
        
    def subscribe(self, session, params=None):
        yield self.agent.subscribe(self.handler,self.feed)
        print("Subscribed to feed: %s"%self.feed)


if __name__ == '__main__':
    agent, runner = ocs_agent.init_ocs_agent('observatory.subscriber')
    subscriber = Subscriber(agent, u'observatory.thermometry.data')
    agent.register_task('sub', subscriber.subscribe)
    runner.run(agent, auto_reconnect=True)    
    