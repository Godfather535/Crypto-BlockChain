from flask import Flask, render_template,jsonify,request
from time import time
from flask_cors import CORS
from collections import OrderedDict
import binascii
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA
from uuid import uuid4
import json
import hashlib
import requests
from urllib.parse import urlparse

MINING_SENDER = 'Block Chain'
MINING_REWARD = 1
MINING_DIFFICULTY = 2

class BlockChain:

    def __init__(self):
        self.transactions = []
        self.chain = []
        self.nodes = set()
        self.node_id = str(uuid4()).replace('-', '')
        self.create_block(0,'00')

    def register_node(self, node_url):
        parsed_url = urlparse(node_url)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def create_block(self,nonce,previous_hash):
        # Adding  a block of transactions to the chain
        block = {
            'block_number' : len(self.chain)+1,
            'timestamp' : time(),
            'transactions' : self.transactions,
            'nonce' : nonce,
            'previous_hash':previous_hash,
        }

        #Reset the transactions for the new block
        self.transactions = []
        self.chain.append(block)
        return block

    def verify_signature_transaction(self, sender_public_key, signature, transaction):
        public_key = RSA.importKey(binascii.unhexlify(sender_public_key))
        verifier = PKCS1_v1_5.new(public_key)
        h = SHA.new(str(transaction).encode('utf8'))
        try:
            verifier.verify(h, binascii.unhexlify(signature))
            return True
        except ValueError:
            return False

    def submit_transaction(self, sender_public_key, recipient_public_key, signature, amount):
        #TODO: Reward the Miner
        #TODO: Signature Validation

        transaction = OrderedDict({
            'sender_public_key': sender_public_key,
            'recipient_public_key' : recipient_public_key,
            'amount' : amount,
        })

        if sender_public_key == MINING_SENDER:
            self.transactions.append(transaction)
            return len(self.chain) + 1
        else:
            #Transaction from wallet to another Wallet
            signature_verification = self.verify_signature_transaction(sender_public_key, signature, transaction)
            if signature_verification:
                self.transactions.append(transaction)
                return len(self.chain) + 1
            else:
                return False

    @staticmethod
    def valid_proof(transactions, last_hash, nonce, difficulty=MINING_DIFFICULTY):
        guess = (str(transactions) + str(last_hash) + str(nonce)).encode('utf8')
        h = hashlib.new('sha256')
        h.update(guess)
        guess_hash = h.hexdigest()

        return guess_hash[:difficulty] == '0' * difficulty


    def proof_of_work(self):
        last_block = self.chain[-1]
        last_hash = self.hash(last_block)
        nonce = 0
        while self.valid_proof(self.transactions, last_hash, nonce) is False:
            nonce += 1

        return nonce

    def valid_chain(self, chain):
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]

            if block['previous_hash'] != self.hash(last_block):
                return False

            transactions = block['transactions'][:-1]
            transaction_elements = ['sender_public_key', 'recipient_public_key', 'amount']
            transactions = [OrderedDict((k, transaction[k]) for k in transaction_elements) for transaction in transactions]


            if not self.valid_proof(transactions, block['previous_hash'], block['nonce'], MINING_DIFFICULTY):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        neighbours = self.nodes
        new_chain = None

        max_length = len(self.chain)
        for node in neighbours:
            response = requests.get('http://' + node + '/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True

        return False

    @staticmethod
    def hash(block):
        #We must to ensure that the dictionary is ordered otherwise we will get in consistent hashes
        block_string = json.dumps(block, sort_keys=True).encode('utf8')
        h = hashlib.new('sha256')
        h.update(block_string)
        return h.hexdigest()

# Instantiate our BlockChain
blockChain = BlockChain()

# Instantiate the Node
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("./index.html")

@app.route("/configure")
def configure():
    return render_template("./configure.html")

@app.route("/transactions/get", methods = ['GET'])
def get_transaction():
    transactions = blockChain.transactions
    response = {'transactions' : transactions}
    return jsonify(response), 200

@app.route("/chain", methods = ['GET'])
def get_chain():
    response = {
        'chain': blockChain.chain,
        'length': len(blockChain.chain)
    }

    return jsonify(response), 200

@app.route("/mine", methods = ['GET'])
def mine():
    # We run the proof of work algorithm
    nonce = blockChain.proof_of_work()

    blockChain.submit_transaction(sender_public_key=MINING_SENDER,
                                  recipient_public_key=blockChain.node_id,
                                  signature='',
                                  amount=MINING_REWARD,
                                  )
    last_block = blockChain.chain[-1]
    previous_hash = blockChain.hash(last_block)
    block = blockChain.create_block(nonce, previous_hash,)

    response = {
        'message':'New block created',
        'block_number':block['block_number'],
        'transactions': block['transactions'],
        'nonce': block['nonce'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

@app.route("/transactions/new", methods = ['POST'])
def new_transaction():
    values = request.form

    #TODO: Check the required fields

    required = ['confirmation_sender_public_key', 'confirmation_recipient_public_key', 'transaction_signature', 'confirmation_amount']
    if not all(k in values for k in required):
        return 'Missing Values', 400

    transaction_results = blockChain.submit_transaction(values['confirmation_sender_public_key'],
                                                        values['confirmation_recipient_public_key'],
                                                        values['transaction_signature'],
                                                        values['confirmation_amount'])

    if transaction_results == False:
        response = {'message': 'Invalid Transaction/Signature'}
        return jsonify(response), 406
    else:
        response = {'message': 'Transaction will be added to the Block ' + str(transaction_results)}
        return jsonify(response), 201

@app.route("/nodes/get", methods = ['GET'])
def get_nodes():
    nodes = list(blockChain.nodes)
    response = {'nodes' : nodes}
    return jsonify(response), 200

@app.route("/nodes/register", methods = ['POST'])
def register_nodes():
    values = request.form
    # 127.0.0.1:5002, 127.0.0.1:5003, 127.0.0.1:5004,
    nodes = values.get('nodes').replace(" ", "").split(',')

    if nodes is None:
        return 'Error: Please supply a valid list of nodes', 400

    for node in nodes:
        blockChain.register_node(node)

    response = {
        'message': 'Nodes have been added',
        'total_nodes': [node for node in blockChain.nodes]
    }

    return jsonify(response), 200

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5001, type=int, help='port to listen to')
    args = parser.parse_args()
    port = args.port
    app.run(host='127.0.0.1', port=port, debug=True)
