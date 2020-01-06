import requests
import re
import time
import datetime
import json
import os
import logging
from functools import wraps
from bs4 import BeautifulSoup
from lxml import etree
from elasticsearch import Elasticsearch

requests.urllib3.disable_warnings()

logging.basicConfig(level=os.getenv('LOGGING_LEVEL', logging.INFO),
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%Y-%m-%d %H:%M')


def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        logging.info('func:%r args:[%r, %r] took: %2.4f sec' % (
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
            logging.debug("[GET_LINK_FROM_INDEX]: {}".format(
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
        logging.error('[GET_NEWS_CONTENT]: {}'.format(e))
        return None

# 取得文章內容


def get_news_info(page, board):
    soup = BeautifulSoup(page, features="html.parser")

    # 取得 作者 看板 標題 時間
    tag_mapping = {"作者": "author", "看板": "board",
                   "標題": "title", "時間": "@timestamp"}
    span_tag = soup.find_all("span", class_="article-meta-tag")
    span_value = soup.find_all("span", class_="article-meta-value")
    page_info = {}
    for i in range(4):

        # 設定時間格式 其餘欄位正常寫入
        if tag_mapping[str(span_tag[i].text)] == "@timestamp":
            date_time = datetime.datetime.strptime(str(span_value[i].text), "%a %b %d %H:%M:%S %Y").isoformat()
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

    while True:
        try:
            create_index = es.indices.create(index=esindex, ignore=400)
            res = es.index(index=esindex, doc_type="_doc", id=docid, body=doc)
            logging.info('[Elastic]: {}'.format(res))
            break
        except Exception as e:
            logging.error('[Elastic]: {}'.format(repr(e)))
            time.sleep(5)
            print("Es Connection Failed Try again")


def main(es_root_index='test'):
    # 從首頁進入並設定cookie
    ptt = "https://www.ptt.cc"
    board = "Gossiping"
    url = 'https://www.ptt.cc/bbs/'+board+'/index.html'
    s = requests.Session()
    s.post(ptt + "/ask/over18", data={'yes': 'yes'})  # 設定18歲cookie
    page = s.get(url).text  # 取得最新頁內容
    page_index = get_page_index(page)  # 取得最新頁index
    ROOT_INDEX = os.getenv('ROOT_INDEX', 'test')
    # print("page_index=", page_index)

    page_index_count = 0
    while True:
        page_uel = 'https://www.ptt.cc/bbs/{}/index{}.html'.format(board, str(page_index-page_index_count))
        # print(page_uel)

        page = s.get(page_uel).text

        try:
            news_List = get_links_from_index(page, board)

            # 此頁文章列表
            for title, link, date, id in news_List:
                # print("Title=", title)
                # print("Date=", date)
                # print("ID=", id)
                # print("Link=", ptt + link, end="\n\n")

                news_page = s.get(ptt + link).text
                try:
                    news_info = get_news_info(news_page, board)

                    # print("Final time => ", news_info["datetime"])
                    logging.debug("[GET_NEWS_INFO]: Final time => {}".format(
                        news_info["@timestamp"]))

                    dd = datetime.datetime.fromisoformat(news_info.get("@timestamp")).strftime('%Y-%m-%d')
                    # dd = datetime.datetime.strptime(
                    #     news_info["datetime"], "%Y-%m-%d %H:%M:%S").strftime('%Y-%m-%d')

                    # 寫入elasticsearch
                    saveES(esindex="{}_{}".format(es_root_index, dd), doc=news_info)

                    # news_info = json.dumps(news_info)
                    # with open("news_info.json", "at", encoding="UTF-8") as fw:
                    #     print(news_info, file=fw)

                except Exception as err:
                    logging.error('[GET_NEWS_INFO] : {}'.format(repr(err)))

                # 取到此版第1頁
                if (page_index-page_index_count) == 1:
                    break  # break for
            else:
                page_index_count += 1
                continue  # continue while
            break  # break while
        except Exception as err:
            logging.error('[GET_LINKS_FROM_INDEX]: {}'.format(repr(err)))
            # 取到此版第1頁
            if (page_index-page_index_count) == 1:
                break  # break while
            else:
                page_index_count += 1
                continue


if __name__ == "__main__":
    try:
        print(os.getenv('ELASTICSEARCH_ENDPOINT'))
        ELASTICSEARCH_ROOT_INDEX = os.getenv('ELASTICSEARCH_ROOT_INDEX','test')
        main(es_root_index=ELASTICSEARCH_ROOT_INDEX)
    except Exception as e:
        logging.error('[Exception]: {}'.format(repr(e)))
