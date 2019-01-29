import consensus
import sqldb
import math

def validateChallenge(block, stake):
    target = consensus.Consensus().target
    if block.hash < stake * target:
        return True
    return False

def validateRound(block, bc):
    chainBlock = bc.getLastblock()
    if block.index > chainBlock.index and block.round > chainBlock.round:
        if validateExpectedRound(block, chainBlock):
            return True
    return False

def validateBlockHeader(block):
    # check block header
    if block.hash == block.calcBlockhash():
            return True
    return False

def validateBlock(block, lastBlock):
    # check block chaining
    if block.prev_hash == lastBlock.hash:
        return True
    return False


def blockPosition(block, bc, stake):
    #check if the block has a valid threshold
    chainPos, bcPos = validatePositionBlock(block, bc, stake)
    if(chainPos):
        return True, bcPos
    else:
        return False, bc

def validatePositionBlock(block, bc, stake):
    i = 0
    while i < consensus.THRESHOLD:
        if(len(bc.chain)> 1):
            bc.chain.pop()
        chainBlock = bc.getLastBlock()
        if(block.prev_hash == chainBlock.prev_hash and 
           chainBlock.round > block.round and 
           validateChallenge(block, stake)):
            return True, bc
        i = i + 1

    return False, bc

def validateChain(bc, chain, stake):
    lastBlock = bc.getLastBlock()
    print(lastBlock.blockInfo())
    for b in chain:
        b=sqldb.dbtoBlock(b)
        if not validateBlockHeader(b): # invalid
                return b, True

        if validateBlock(b, lastBlock):
            if validateChallenge(b, stake):
                lastBlock=b
                bc.addBlocktoBlockchain(b)
                sqldb.writeBlock(b)
                sqldb.writeChain(b)
        else: # fork
            return b, False
    return None, False

def validateExpectedRound(block, lastBlock):
    
    calculated_rounds = math.floor((lastBlock.arrive_time - block.arrive_time)/consensus.TIMEOUT)
    expected_round = lastBlock.round + calculated_rounds

    if expected_round == block.round:
        return True
    else:
        return False