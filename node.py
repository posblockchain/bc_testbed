#!/usr/bin/env python

import zmq
import threading
import time
import argparse
from configparser import SafeConfigParser
import block
import blockchain
import consensus
import sqldb
import pickle
from collections import deque, Mapping
import logging
import rpc.messages as rpc
import hashlib
import datetime
import math
import validations

#TODO blockchain class and database decision (move to only db solution?)
#TODO peer management and limit (use a p2p library - pyre, kademlia?)
#TODO serialization/deserialization functions, change pickle to json?
#TODO add SQL query BETWEEN in rpcServer
#TODO check python 3+ compatibility

class StopException(Exception):
    pass

class Node(object): 
    """ Main class """

    ctx = None

    def __init__(self, ipaddr='127.0.0.1', port=9000):
        self.ipaddr = ipaddr
        self.port = int(port)
        self.balance = 1
        self.stake = 0
        self.synced = False
        self.peers = deque()
        self.bchain = blockchain.Blockchain()
        # ZMQ attributes
        self.ctx = zmq.Context.instance()
        self.poller = zmq.Poller()
        self.reqsocket = self.ctx.socket(zmq.REQ)
        self.repsocket = self.ctx.socket(zmq.REP)
        self.router = self.ctx.socket(zmq.REQ)
        self.rpcsocket = self.ctx.socket(zmq.REP)
        self.psocket = self.ctx.socket(zmq.PUB)
        self.subsocket = self.ctx.socket(zmq.SUB)
        self.subsocket.setsockopt(zmq.SUBSCRIBE, b'')
        self.poller.register(self.reqsocket, zmq.POLLIN)
        self.poller.register(self.router, zmq.POLLIN)
        self.reqsocket.setsockopt(zmq.REQ_RELAXED, 1)
        # Flags and thread events
        self.k = threading.Event()
        self.e = threading.Event()
        self.f = threading.Event()
        self.start = threading.Event()

    # Node as client
    def connect(self,d_ip='127.0.0.1',d_port=9000):
        self.subsocket.connect("tcp://%s:%s" % (d_ip, d_port))
        self.reqsocket.connect("tcp://%s:%s" % (d_ip, d_port+1))

    def disconnect(self,d_ip='127.0.0.1',d_port=9000):
        self.subsocket.disconnect("tcp://%s:%s" % (d_ip, d_port))
        self.reqsocket.disconnect("tcp://%s:%s" % (d_ip, d_port+1))

    # Node as server
    def bind(self, socket, ip=None, port=None):
        if port and ip:
            socket.bind("tcp://%s:%s" % (ip, port))
        elif port:
            socket.bind("tcp://%s:%s" % (self.ipaddr, port))
        else:
            socket.bind("tcp://%s:%s" % (self.ipaddr, self.port))

    def close(self):
        """ Terminate and close ZMQ sockets and context """
        self.psocket.close(linger=0)
        self.subsocket.close(linger=0)
        self.repsocket.close(linger=0)
        self.rpcsocket.close(linger=0)
        self.reqsocket.close(linger=0)
        self.router.close(linger=0)
        self.ctx.term()

    def addPeer(self, ipaddr):
        """ Add ipaddr to peers list and connect to its sockets  """
        peer = ipaddr if isinstance(ipaddr,Mapping) else {'ipaddr': ipaddr}
        if peer not in self.peers:
            self.peers.appendleft(peer)
            self.connect(d_ip=peer['ipaddr'],d_port=self.port)
            return "Peer %s connected" % peer['ipaddr']
        else:
            logging.warning("Peer %s already connected" % peer['ipaddr'])
            return "Peer %s already connected" % peer['ipaddr']

    def removePeer(self, ipaddr):
        """ Remove peer with ipaddr and disconnect to its sockets  """
        peer = ipaddr if isinstance(ipaddr,Mapping) else {'ipaddr': ipaddr}
        try:
            self.peers.remove(peer)
            self.disconnect(d_ip=peer['ipaddr'],d_port=self.port)
            time.sleep(1)
        except ValueError:
            logging.warning("Peer %s not connected" % peer['ipaddr'])
            return "Peer %s not connected" % peer['ipaddr']
        return "Peer %s removed" % peer['ipaddr']

    def getPeers(self):
        return self.peers

    def addBalance(self, value):
        self.balance = self.balance + value

    def listen(self):
        """ Listen to block messages in a SUB socket
            Message frames: [ 'block', ip, block data ]
        """
        self.bind(self.psocket)
        while True and not self.k.is_set():
            try:
                msg, ip, block_recv = self.subsocket.recv_multipart()
                self.f.clear()
                newChain = False
                
                # serialize
                b = pickle.loads(block_recv)
                logging.info("Got block %s miner %s" % (b.hash, ip))
                b.arrive_time = str(datetime.datetime.now())
                # Verify block
                if validations.validateBlockHeader(b):
                    logging.debug('valid block header')
                    lb = self.bchain.getLastBlock()
                                   
                    if ((b.index - lb.index == 1) and 
                         validations.validateBlock(b, lb) and 
                         validations.validateRound(b, self.bchain) and 
                         validations.validateChallenge(b, self.stake)):
                        self.e.set()
                        self.bchain.addBlocktoBlockchain(b)
                        sqldb.writeBlock(b)
                        sqldb.writeChain(b)
                        # rebroadcast
                        #logging.debug('rebroadcast')
                        self.psocket.send_multipart([consensus.MSG_BLOCK, ip, pickle.dumps(b, 2)])
                    elif b.index - lb.index > 1:
                        self.synced = False
                        self.sync(b, ip)
                    elif b.index == lb.index:
                        if b.hash == lb.hash:
                            logging.debug('retransmission')
                        else:
                            logging.debug('fork')
                            if (validations.validateBlock(b, lb) and 
                               validations.validateChallenge(b, self.stake)):
                                # double entry
                                sqldb.writeBlock(b)
                    else:
                        # ignore old block
                        logging.debug('old')
                else:
                    logging.debug('invalid block')
                #
                self.f.set()
            except (zmq.ContextTerminated):
                break

    def mine(self, cons):
        """ Create and send block in PUB socket based on consensus """
        name = threading.current_thread().getName()
        
        while True and not self.k.is_set():
            
            # move e flag inside generate?
            self.start.wait()
            self.f.wait()
            
            lastblock = self.bchain.getLastBlock()
            node = hashlib.sha256(self.ipaddr).hexdigest()
            self.stake = self.balance
           
            # find new block
            b = cons.generateNewblock(lastblock, node, self.stake, self.e)

            if b and not self.e.is_set():
                newchain, self.bchain = validations.validatePositionBlock(b, self.bchain, self.stake)
                logging.info("Mined block %s" % b.hash)
                b.arrive_time = str(datetime.datetime.now())
                sqldb.writeBlock(b)
                sqldb.writeChain(b)
                self.bchain.addBlocktoBlockchain(b)
                self.psocket.send_multipart([consensus.MSG_BLOCK, self.ipaddr, pickle.dumps(b, 2)])
            else:
                self.e.clear()

    def probe(self):
        for i in self.peers:
            x = self.hello()
            if not x:
                self.removePeer(i)

    def sync(self, rBlock=None, address=None):
        """ Syncronize with peers and validate chain
        rBlock -- can be passed as argument to sync based on that block index instead of requesting
        address -- try to force requests to use this ip address
        """
        self.synced = True
        logging.debug('syncing...')
        # Request before sync
        if not rBlock:
            rBlock = self.bchain.getLastBlock()
            # limit number of peers request
            for i in xrange(0,min(len(self.peers),3)):
                i+=1
                logging.debug('request #%d' % i)
                b, ip = self.reqLastBlock()
                if b:
                    logging.debug('Block index %s' % b.index)
                if (b and (b.index > rBlock.index)):
                    rBlock = b
                    address = ip
                    logging.debug('Best index %s with ip %s' % (b.index, ip))
        last = self.bchain.getLastBlock()
        # Sync based on rBlock
        if (rBlock.index > last.index):
            self.e.set()
            if ((rBlock.index-last.index == 1) and 
                validations.validateBlock(rBlock, last) and 
                validations.validateBlockHeader(rBlock) and
                validations.validateChallenge(rBlock, self.stake)):
                logging.debug('valid block')
                sqldb.writeBlock(rBlock)
                sqldb.writeChain(rBlock)
                self.bchain.addBlocktoBlockchain(rBlock)
            else:
                chain = self.reqBlocks(last.index+1, rBlock.index, address)
                if  chain:
                    # validate and write
                    b_error, h_error = validations.validateChain(self.bchain, chain, self.stake)
                    # update last block
                    last = self.bchain.getLastBlock()
                    # if b_error is diffent to None
                    if b_error:
                        # TODO review from next line, because it is strange
                        # if h_error is false and block index equal last block index plus one
                        if not h_error and b_error.index == last.index:
                            logging.debug('fork')
                            sqldb.writeBlock(b_error)
                            # trying to solve and pick a fork
                            n = self.recursiveValidate(b_error)
                            if n:                                
                                self.bchain.chain.clear() # TODO change this and refactor
                                for i in xrange(n.index,last.index+1):
                                    logging.debug('updating chain')
                                    if i == 1:
                                        sqldb.replaceChain(n)
                                        self.bchain.addBlocktoBlockchain(n)
                                    else:
                                        n = sqldb.forkUpdate(i)
                                        sqldb.replaceChain(n)
                                        self.bchain.addBlocktoBlockchain(sqldb.dbtoBlock(n))
                                validations.validateChain(self.bchain, chain, self.stake)
                        else:
                            logging.debug('invalid') # request again
                            new = self.reqBlock(b_error.index)
                            self.sync(new)
        logging.debug('synced')

    def recursiveValidate(self, blockerror):
        index = blockerror.index - 1
        pblock = sqldb.dbtoBlock(sqldb.blockQuery(['',index])) # previous block
        trials = 3
        while index and trials:
            logging.debug('validating index %s' % index)
            new = self.reqBlock(index)
            if new and validations.validateBlockHeader(new):
                sqldb.writeBlock(new)
                if validations.validateBlock(new, pblock) and validations.validateChallenge(new, self.stake):
                    logging.debug('returning')
                    return new
                else:
                    index -= 1
                    pblock = sqldb.dbtoBlock(sqldb.blockQuery(['',index]))
            else:
                trials -= 1
        return new

    def messageHandler(self):
        """ Consensus messages in REQ/REP pattern
            Messages frames: REQ [ type, opt ]
                             REP [ ip, data ] 
        """
        self.bind(self.repsocket, port=self.port+1)
        time.sleep(1)
        while True and not self.k.is_set():
            try:
                messages = self.repsocket.recv_multipart()
            except zmq.ContextTerminated:
                break
            reply = consensus.handleMessages(self.bchain, messages)
            self.repsocket.send_multipart([self.ipaddr, pickle.dumps(reply, 2)])

    def rpcServer(self, ip='127.0.0.1', port=9999):
        """ RPC-like server to interact with rpcclient.py """
        self.bind(self.rpcsocket, ip, port)
        time.sleep(1)
        while True:
            try:
                messages = self.rpcsocket.recv_multipart()
            except zmq.ContextTerminated:
                break
            time.sleep(1)
            cmd = messages[0].lower()
            if cmd == rpc.MSG_LASTBLOCK:
                b = self.bchain.getLastBlock()
                self.rpcsocket.send(b.blockInfo())
            elif cmd == rpc.MSG_BLOCKCHAIN:
                b = self.bchain.Info()
                self.rpcsocket.send(b)
            elif cmd == rpc.MSG_BLOCK:
                b = sqldb.dbtoBlock(sqldb.blockQuery(messages))
                self.rpcsocket.send(b.blockInfo() if b else 'error')
            elif cmd == rpc.MSG_BLOCKS:
                l = sqldb.blocksListQuery(messages)
                blocks = []
                for b in l:
                    blocks.append(sqldb.dbtoBlock(b).blockInfo())
                self.rpcsocket.send_pyobj(blocks)
            elif cmd == rpc.MSG_ADD:
                m = self.addPeer(messages[1])
                self.rpcsocket.send_string(m)
            elif cmd == rpc.MSG_REMOVE:
                m = self.removePeer(messages[1])
                self.rpcsocket.send_string(m)
            elif cmd == rpc.MSG_PEERS:
                self.rpcsocket.send_pyobj(self.getPeers())
            elif cmd == rpc.MSG_START:
                self.rpcsocket.send_string('Starting mining...')
                self.start.set()
                self.f.set()
            elif cmd == rpc.MSG_STOP:
                self.start.clear()
                self.rpcsocket.send_string('Stopping mining...')
            elif cmd == rpc.MSG_EXIT:
                self.rpcsocket.send_string('Exiting...')
                raise StopException
            elif cmd == rpc.MSG_BALANCE:
                self.addBalance(int(messages[1]))
                self.rpcsocket.send_string('Node Balance is ' + str(self.balance))    
            else:
                self.rpcsocket.send_string('Command unknown')
                logging.warning('Command unknown')

# Client request-reply functions

    def _poll(self, socket=None):
        # Poll socket for 5s checking if any arriving reply messages
        s = socket if socket else self.reqsocket
        try:
            evts = dict(self.poller.poll(5000))
        except KeyboardInterrupt:
            return None, None
        if s in evts and evts[s] == zmq.POLLIN:
            m = s.recv_multipart()
            return pickle.loads(m[-1]), m[-2]
        else:
            logging.debug('No response from node (empty pollin evt)')
            return None, None

    def reqLastBlock(self):
        """ Messages frames: [ 'getlastblock', ] """
        self.reqsocket.send_multipart([consensus.MSG_LASTBLOCK,])
        logging.debug('Requesting most recent block')
        m, address = self._poll()
        return sqldb.dbtoBlock(m), address

    def reqBlock(self, index):
        """ Messages frames: [ 'getblock', index ] """
        self.reqsocket.send_multipart([consensus.MSG_BLOCK, str(index)])
        logging.debug('Requesting block index %s' % index)
        m = self._poll()[0]
        return sqldb.dbtoBlock(m)

    def reqBlocks(self, first, last, address=None):
        """ Messages frames: [ 'getblocks', from index, to index ] """
        if address:
            # using another socket for direct ip connect, avoiding round-robin
            self.router.connect("tcp://%s:%s" % (address, self.port+1))
            time.sleep(1)
            logging.debug('Requesting blocks %s to %s', first, last)
            self.router.send_multipart([consensus.MSG_BLOCKS, str(first), str(last)])
            m = self._poll(self.router)[0]
            self.router.disconnect("tcp://%s:%s" % (address, self.port+1))
        else:
            self.reqsocket.send_multipart([consensus.MSG_BLOCKS, str(first), str(last)])
            logging.debug('Requesting blocks %s to %s', first, last)
            m = self._poll()[0]
        return m

    def hello(self):
        """ Messages frames: [ 'hello', ] """
        self.reqsocket.send_multipart([consensus.MSG_HELLO,])
        logging.debug('Probing peer alive')
        m = self._poll()[0]
        return m

# Main program

_LOG_LEVEL_STRINGS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

def _log_level_to_int(loglevel):
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise argparse.ArgumentTypeError('Invalid log level: %s' % loglevel)
    return numeric_level

def main():
    # Argument and command-line options parsing
    parser = argparse.ArgumentParser(description='Blockchain simulation')
    parser.add_argument('-i', '--ip', metavar='ip', dest='ipaddr',
                        help='Specify listen IP address', default='127.0.0.1')
    parser.add_argument('-p', '--port', metavar='port', dest='port',
                        help='Specify listen port', default=9000)
    parser.add_argument('--peers', dest='peers', nargs='*',
                        help='Specify peers IP addresses', default=[])
    parser.add_argument('--miner', dest='miner', action='store_true',
                        help='Start the node immediately mining')
    parser.add_argument('--log', dest='loglevel', type=_log_level_to_int, nargs='?', default='warning',
                        help='Set the logging output level {0}'.format(_LOG_LEVEL_STRINGS))
    parser.add_argument ('-c', '--config', dest='config_file', default='node.conf', type=str,
                        help='Specify the configuration file')
    args = parser.parse_args()
    args.diff = 5
    # Configuration file parsing (defaults to command-line arguments if not exists)
    cfgparser = SafeConfigParser({'ip': args.ipaddr, 'port': str(args.port), 'peers': args.peers, 'miner': str(args.miner).lower(), 'loglevel': 'warning', 'diff': '5'})
    if cfgparser.read(args.config_file):
        args.peers = cfgparser.get('node','ip')
        args.port = int(cfgparser.get('node','port'))
        args.peers = cfgparser.get('node','peers').split('\n')
        args.miner = cfgparser.getboolean('node','miner')
        args.diff = int(cfgparser.get('node','diff'))
        args.loglevel = _log_level_to_int(cfgparser.get('node','loglevel'))
    # File logging
    logging.basicConfig(filename='log/example.log', filemode='w', level=_log_level_to_int('debug'),
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%d/%m/%Y %I:%M:%S')
    # set up logging to console
    console = logging.StreamHandler()
    console.setLevel(args.loglevel)
    logging.getLogger('').addHandler(console)

    threads = []
    #sqldb.databaseLocation = 'blocks/blockchain.db'
    cons = consensus.Consensus(difficulty=args.diff)
    n = Node(args.ipaddr, args.port)

    # Connect to predefined peers
    if args.peers:
        iplist = args.peers if isinstance(args.peers, list) else [args.peers]
        for ipaddr in iplist:
            n.addPeer(ipaddr)
    else: # Connect to localhost
        logging.info('Connecting to localhost...')
        n.connect()
    time.sleep(1)

    # Connect and check own node database
    logging.info('checking database')
    sqldb.dbConnect()
    n.bchain = sqldb.dbCheck()

    # Thread to listen request messages
    msg_thread = threading.Thread(name='REQ/REP', target=n.messageHandler)
    msg_thread.start()
    threads.append(msg_thread)

    # Thread to listen broadcast messages
    listen_thread = threading.Thread(name='PUB/SUB', target=n.listen)
    listen_thread.start()
    threads.append(listen_thread)
    #

    # Check peers most recent block
    n.sync()

    # Miner thread
    miner_thread = threading.Thread(name='Miner', target=n.mine,
         kwargs={'cons': cons})
    miner_thread.start()
    threads.append(miner_thread)

    if args.miner:
        n.start.set()
        n.f.set()

    # Main program thread
    try:
        while True:
            # rpc-like commands
            n.rpcServer()
    # Exit main and threads
    except (KeyboardInterrupt, StopException):
        pass
    finally:
        n.k.set()
        n.e.set()
        n.f.set()
        n.start.set()
        n.close()
        for t in threads:
           t.join()
        print(n.bchain.Info())

if __name__ == '__main__':
    main()
