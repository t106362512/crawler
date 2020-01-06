import requests
import re
import time
import datetime
import json
import os
import sys
import logging
import multiprocessing
from functools import wraps
from bs4 import BeautifulSoup
from lxml import etree
from elasticsearch import Elasticsearch
from joblib import Parallel, delayed
# from tqdm import tqdm #LineBar

requests.urllib3.disable_warnings()  # disable cert warninng

# logging.basicConfig(level=os.getenv('LOGGING_LEVEL', logging.INFO),
#                     format='%(asctime)s %(levelname)s %(message)s',
#                     datefmt='%Y-%m-%d %H:%M')


def get_logger():
    requests.urllib3.disable_warnings()
    logger = logging.getLogger()
    logger.setLevel(level=os.getenv('LOGGING_LEVEL', logging.INFO))
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]', datefmt='%Y-%m-%d %H:%M')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        # logging.info('func:%r args:[%r, %r] took: %2.4f sec' % (
        #     f.__name__, str(args)[0:100], str(kwargs)[0:100], end-start))
        get_logger().info('func:%r args:[%r, %r] took: %2.4f sec' % (
            f.__name__, str(args)[0:100], str(kwargs)[0:100], end-start))
        return result
    return wrapper


def get_page_index(page):
    soup_btn = BeautifulSoup(page, features="html.parser")
    divs = soup_btn.find_all('div', class_='btn-group btn-group-paging')

    for div in divs[0].find_all('a'):
        # print(div)
        if "上頁" in str(div):
            Previous = div['href']
            Previous = re.search(r"index(\d*)", Previous)
            Previous = Previous.group().replace("index", "")
            return int(Previous)+1
    return None

# 取得文章標題與連結
# Return list


@timing
def get_links_from_index(page, board):
    # 發現文章位於 div 標籤的 r-ent class先往下解析一層
    soup = BeautifulSoup(page, features="html.parser")
    divs = soup.find_all('div', class_='r-ent')

    linkList = list()
    for div in divs:
        # print(div)

        soup_rent = BeautifulSoup(str(div), features="html.parser")

        # 解析標題的div結構
        title = soup_rent.find_all('div', class_='title')
        news_title = title[0].text.strip()

        if '公告' in news_title or '協尋' in news_title:
            continue

        try:
            # 取得標題文章內文之連結
            news_link = title[0].find('a')['href'].strip()
        except:
            continue

        date = soup_rent.find_all('div', class_='date')
        news_date = date[0].text.strip()

        news_id = re.findall(board+r"\/(.*)\.html", news_link)
        if len(news_id) == 1:
            news_id = news_id[0]
        else:
            # logging.debug("[GET_LINK_FROM_INDEX]: {}".format(
            #     "Not find, or can't match regex only one"))
            get_logger().debug("[GET_LINK_FROM_INDEX]: {}".format(
                "Not find, or can't match regex only one"))
            news_id = None

        linkList.append([news_title, news_link, news_date, news_id])

    # 因為每一個 index.html中的文章，最新的那篇是在最底下，所以做個 reversed
    # 這樣最新的文章就會是在 linkList[0]
    linkList = list(reversed(linkList))

    return linkList

# 對個文章原始碼進行處理


def get_news_content(link, html):
    soup = BeautifulSoup(html, features="html.parser")
    meta = soup.find_all('span', class_="article-meta-value")
    try:
        author = meta[0].text
        title = meta[2].text
        time = meta[3].text
    except:
        return None
    txt = soup.find('div', id="main-content")
    f2 = soup.find_all('span', class_="f2")
    cut_link = ""

    for i in f2:
        if link in i.text:
            cut_link = i.text
            break

    txt_next = txt.text.split(meta[3].text)

    txt_final = txt_next[1].split(cut_link)
    cont = txt_final[0]

    txt_next = txt.text.split(meta[3].text)
    try:
        news = {
            'Title': title,
            'URL': link,
            'Author': author,
            'Description': cont,
        }
        # print(news)
        return news

    except Exception as e:
        # logging.error('[GET_NEWS_CONTENT]: {}'.format(repr(e)))
        get_logger().error('[GET_NEWS_CONTENT]: {}'.format(repr(e)))
        return None

# 取得文章內容


def get_news_info(page, board):
    soup = BeautifulSoup(page, features="html.parser")

    # 取得 作者 看板 標題 時間
    tag_mapping = {"作者": "author", "看板": "board",
                   "標題": "title", "時間": "@timestamp", "R作者": "rauthor", "站內": "insite"}
    span_tag = soup.find_all("span", class_="article-meta-tag")
    span_value = soup.find_all("span", class_="article-meta-value")
    page_info = {}
    for i in range(4):
        # 設定時間格式 其餘欄位正常寫入
        if tag_mapping[str(span_tag[i].text)] == "@timestamp":
            date_time = datetime.datetime.strptime(
                str(span_value[i].text), "%a %b %d %H:%M:%S %Y").isoformat()
            page_info.setdefault(tag_mapping[str(span_tag[i].text)], date_time)
        else:
            page_info.setdefault(
                tag_mapping[str(span_tag[i].text)], str(span_value[i].text))
    # print(page_info)

    # 取得內文
    selector = etree.HTML(page)
    text_index = 1
    article = ""
    while True:
        results = selector.xpath(
            '//*[@id="main-content"]/text()['+str(text_index)+']')
        if results:
            for result in results:
                article += result.replace("\n", "").replace("  ", "").strip()
                # print(result)
            # print(article)
            text_index += 1
        else:
            break
    page_info.setdefault("article", article)
    # print(page_info)

    # 取得IP
    span_ip = soup.find("span", class_="f2", text=re.compile(r"發信站"))
    ip_find = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', span_ip.text)
    ip = None
    if ip_find:
        ip = ip_find.group(0)
    page_info.setdefault("ip", ip)

    # 取得url
    span_urls = soup.find_all("span", class_="f2")
    for span_url in span_urls:
        if(span_url.find('a') != None):
            try:
                page_info.setdefault("url", span_url.find('a')['href'])
            except:
                page_info.setdefault("url", None)

    # 取得文章 ID
    span_urls = soup.find_all("span", class_="f2")
    for span_url in span_urls:
        if(span_url.find('a') != None):
            try:
                news_id = re.findall(board+r"\/(.*)\.html",
                                     span_url.find('a')['href'])
                if len(news_id) == 1:
                    news_id = news_id[0]
                else:
                    # print("Not find, or can't match regex only one")
                    logging.debug("Not find, or can't match regex only one")
                    news_id = None
                page_info.setdefault("id", news_id)
            except:
                page_info.setdefault("id", None)

    # 取得留言 推文
    div_pushs = soup.find_all("div", class_="push")
    # print(div_pushs)

    push_dict = list()
    push_index = 0
    for div_push in div_pushs:
        push_info = {}
        push_info.setdefault("push_tag", div_push.find(
            'span', class_=re.compile(r"push-tag")).text.strip())

        push_info.setdefault("push_userid", div_push.find(
            'span', class_=re.compile(r"push-userid")).text.strip())

        push_info.setdefault("push_content", div_push.find(
            'span', class_=re.compile(r"push-content")).text.replace(": ", "").strip())

        push_ip = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', div_push.find(
            'span', class_=re.compile(r"push-ipdatetime")).text.strip())
        ip = None
        if push_ip != None:
            ip = push_ip.group(0)
        push_info.setdefault("push_ip", ip)

        push_datetime = re.search(
            r'\d\d/\d\d \d\d:\d\d', div_push.find('span', class_=re.compile(r"push-ipdatetime")).text.strip())
        timedate = None
        if push_datetime:
            timedate = push_datetime.group(0)
        push_info.setdefault("push_datetime", timedate)

        push_dict.append(push_info)

    page_info.setdefault("push", push_dict)

    # print(page_info)
    return page_info

# docid 文章寫入ES指定的ID 也可不只定
# doc 文章寫入的本體


@timing
def saveES(esindex, doc, docid=None):
    ELASTICSEARCH_ENDPOINT = os.getenv('ELASTICSEARCH_ENDPOINT')
    ELASTICSEARCH_USER = os.getenv('ELASTICSEARCH_USER')
    ELASTICSEARCH_PASSWD = os.getenv('ELASTICSEARCH_PASSWD')
    es = Elasticsearch([ELASTICSEARCH_ENDPOINT],
                       http_auth=(ELASTICSEARCH_USER, ELASTICSEARCH_PASSWD),
                       scheme="https",
                       port=9200, verify_certs=False)

    for i in range(1,4):
        try:
            requests.urllib3.disable_warnings()
            create_index = es.indices.create(index=esindex, ignore=400)
            res = es.index(index=esindex, doc_type="_doc", id=docid, body=doc)
            # logging.info('[Elastic]: {}'.format(res))
            get_logger().info('[Elastic]: {}'.format(res))
            break
        except Exception as e:
            # logging.error('[Elastic]: {}'.format(repr(e)))
            get_logger().error('[Elastic]:Time:{}, {}'.format(str(i),repr(e)))
            time.sleep(5)
            print("Es Connection Failed Try again")


def get_once_page_result(page_index: int, board: str = "Gossiping", elasticsearch_root_index: str = "test"):

    se = requests.Session()
    se.post("https://www.ptt.cc/ask/over18",
            data={'yes': 'yes'})  # 設定18歲cookie
    ptt = "https://www.ptt.cc"
    page_url = 'https://www.ptt.cc/bbs/{}/index{}.html'.format(
        board, str(page_index))

    page = se.get(page_url).text

    try:
        news_List = get_links_from_index(page, board)

        # 此頁文章列表
        for title, link, date, id in news_List:

            news_page = se.get(ptt + link).text
            try:
                news_info = get_news_info(news_page, board)

                # logging.debug("[GET_NEWS_INFO]: Final time => {}".format(
                #     news_info["@timestamp"]))

                get_logger().debug("[GET_NEWS_INFO]: Final time => {}".format(
                    news_info["@timestamp"]))

                dd = datetime.datetime.fromisoformat(
                    news_info.get("@timestamp")).strftime('%Y-%m-%d')

                # 寫入elasticsearch
                saveES(esindex="{}_{}".format(elasticsearch_root_index, dd), doc=news_info)

                # news_info = json.dumps(news_info)
                # with open("news_info.json", "at", encoding="UTF-8") as fw:
                #     print(news_info, file=fw)

            except AttributeError as e:
                # logging.warning('[GET_NEWS_INFO] : {}'.format(repr(e)))
                get_logger().debug('[GET_NEWS_INFO] : {}'.format(repr(e)))

            except Exception as err:
                # logging.error('[GET_NEWS_INFO] : {}'.format(repr(err)))
                get_logger().error('[GET_NEWS_INFO] : {}'.format(repr(err)))

    except Exception as err:
        # logging.error('[GET_LINKS_FROM_INDEX]: {}'.format(repr(err)))
        get_logger().error('[GET_LINKS_FROM_INDEX]: {}'.format(repr(err)))
    return news_List


def main(elasticsearch_root_index: str = 'test', ptt_board: str = 'Gossiping', ptt_start_page_index: int = 0, ptt_end_page_index: int = 0):
    # 從首頁進入並設定cookie
    requests.urllib3.disable_warnings()
    s = requests.Session()
    s.post("https://www.ptt.cc/ask/over18", data={'yes': 'yes'})  # 設定18歲cookie
    latest_url = 'https://www.ptt.cc/bbs/{}/index.html'.format(ptt_board)
    latest_page = s.get(latest_url).text  # 取得最新頁內容
    st_page_index = ptt_start_page_index if ptt_start_page_index > 0 else 1
    en_page_index = ptt_end_page_index if ptt_end_page_index > 0 else get_page_index(
        latest_page)

    num_cores = multiprocessing.cpu_count()
    results = Parallel(n_jobs=num_cores)(delayed(get_once_page_result)(elasticsearch_root_index=elasticsearch_root_index
        , board=ptt_board, page_index=i) for i in range(st_page_index, en_page_index))
    # logging.info('[MAIN-COMPELTE_LIST]: {}'.format(results))
    get_logger().info('[MAIN-COMPELTE_LIST]: {}'.format(results))


if __name__ == "__main__":
    try:
        ELASTICSEARCH_ROOT_INDEX = os.getenv(
            'ELASTICSEARCH_ROOT_INDEX', 'test')
        PTT_BOARD = os.getenv('PTT_BOARD', 'Gossiping')
        PTT_START_PAGE_INDEX = int(os.getenv('PTT_START_PAGE_INDEX', 0))
        PTT_END_PAGE_INDEX = int(os.getenv('PTT_END_PAGE_INDEX', 0))
        main(elasticsearch_root_index=ELASTICSEARCH_ROOT_INDEX, ptt_board=PTT_BOARD,
             ptt_start_page_index=PTT_START_PAGE_INDEX, ptt_end_page_index=PTT_END_PAGE_INDEX)
    except Exception as e:
        # logging.error('[Exception]: {}'.format(repr(e)))
        get_logger().error('[Exception]: {}'.format(repr(e)))
