# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime
# third-party
import requests
# third-party
from flask import request, render_template, jsonify, redirect

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting, app, celery, Util, py_queue, py_urllib

# 패키지
from .plugin import P
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
from .utility import Utility
from .model import ModelWVDItem
#########################################################


class QueueChromeRequest(object):

    def __init__(self, module):
        self.module = module
        self.queue = py_queue.Queue()
        self.queue_wait_thread = threading.Thread(target=self.queue_wait_thread_function, args=())
        self.queue_wait_thread.daemon = True
        self.queue_wait_thread.start()
        self.enqueue_thread = None        
       

    def queue_wait_thread_function(self):
        while True:
            try:
                logger.debug('!!!!!!!!!!!!!!!!!!!!!!!!QueueChromeRequest wait..')
                db_id = self.queue.get()
                self.process_chrome_request(db_id)
                time.sleep(2)
                self.queue.task_done()    
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    def process_chrome_request(self, db_id):
        db_item = ModelWVDItem.get_by_id(db_id)
        logger.debug('process_chrome_request : %s', db_item)
        ret = self.send_url(db_item.url)
        if ret['ret'] == 'success':
            db_item.status = 'send_url_success'
            db_item.save()
        else:
            self.queue.put(db_item.id)
    
    # 테스트로 호출 될 수 있음.
    def send_url(self, url):
        for i in range(5):
            try:
                server_url = '{server_ddns}/widevine_downloader/api/server/start'.format(server_ddns=ModelSetting.get('client_server_ddns'))
                data={'apikey':ModelSetting.get('client_server_apikey'), 'url':url, 'client_ddns':SystemModelSetting.get('ddns')}
                return requests.post(server_url, data=data).json()
            except Exception as e: 
                P.logger.error('Exception:%s', e)
                P.logger.error(traceback.format_exc())
                ret = {'ret':'warning', 'msg': str(e)}
            time.sleep(10)
        return ret
    

    def enqueue(self):
        queue_list = list(self.queue.queue)
     
        for db_item in ModelWVDItem.get_items_by_status('ready'):
            already_exist = False
            for queue_id in queue_list:
                if queue_id == db_item.id:
                    already_exist = True
                    break
            if already_exist == False:
                self.queue.put(db_item.id)

    def enqueue_one(self,):
        queue_list = list(self.queue.queue)
     
        for db_item in ModelWVDItem.get_items_by_status('ready'):
            already_exist = False
            for queue_id in queue_list:
                if queue_id == db_item.id:
                    already_exist = True
                    break
            if already_exist == False:
                self.queue.put(db_item.id)


    def add_request_url(self, url, memo):
        db_item = ModelWVDItem()
        db_item.url = url
        db_item.memo = memo
        for site in self.module.queue_download.site_list:
            match = site.url_regex.search(url)
            if match:
                db_item.site = site.name
                db_item.code = match.group('code')
                break
        logger.debug('site:[%s] code:[%s]', db_item.site, db_item.code)
        if db_item.site is not None:
            tmp = ModelWVDItem.get_item_by_site_and_code(db_item.site, db_item.code)
            if tmp is None:
                db_item.save()
                ret = {'ret':'success', 'msg':u'URL을 추가하였습니다.'}
                self.queue.put(db_item.id)
            else:
                ret = {'ret':'warning', 'msg':u'이미 같은 코드가 목록에 있습니다.'}
        else:
            ret = {'ret':'warning', 'msg':u'처리할 수 없는 URL입니다.'}
        return ret