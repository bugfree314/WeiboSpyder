import re
import json
import requests
from pandas import DataFrame as df
import datetime as dt
from bs4 import BeautifulSoup
from logging import Logger

time_pat = '%a %b %d %H:%M:%S %z %Y'
cookies_path = './weibo_cookies.txt'


def set_cookies(cookies: str):
    with open(cookies_path, 'w+') as fp:
        fp.write(cookies)


def _get_cookies_from_file():
    with open(cookies_path, 'r') as fp:
        cfg = fp.read()
    return cfg


_headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Cookie": ''
}


def set_headers():
    _headers.update({'Cookie': _get_cookies_from_file()})


def get_headers():
    return _headers


def get_hotband():
    """
    热搜榜

    return a tuple of dict:
        0. hotgov:
            dict:mid,word,url
        1. band_list:
            list of dict:
                key:word,category,num,mid,onboard_time
    """

    url = "https://weibo.com/ajax/statuses/hot_band"
    r = requests.get(url)
    assert r.status_code == 200
    hotband_raw_data = json.loads(r.content)['data']
    if 'hotgov' in hotband_raw_data:
        hotgov = {
            'mid': hotband_raw_data['hotgov']['mid'],
            'word': hotband_raw_data['hotgov']['word'],
            'url': hotband_raw_data['hotgov']['url']
        }
    else:
        hotgov = {}
    band_list_raw = hotband_raw_data['band_list']
    band_list = [{
        'word': item['word'],
        'category':item['category'],
        'num':item['num'],
        'mid':item['mid'],
        'onboard_time':dt.datetime.fromtimestamp(item['onboard_time']).isoformat()
    } for item in band_list_raw if 'category' in item]
    return hotgov, band_list


def get_topicband():
    """
    话题榜

    return a list of dict:
        key:topic,claim:{uid,user},mention,read,summary,category,mid
    """
    url = 'https://weibo.com/ajax/statuses/topic_band'
    r = requests.get(url)
    assert r.status_code == 200
    topicband_raw_data = json.loads(r.content)['data']['statuses']
    keys = ('topic', 'mention', 'read', 'category')
    topicband = [{k: item[k] for k in keys} for item in topicband_raw_data]
    return topicband


def get_allGroups():
    """
    获取分组

    return a tuple of dict:
        榜单分组 group_band，类别分组 group_category
        key:value --> title:{'gid','containerid'}
    """
    url = 'https://weibo.com/ajax/feed/allGroups'

    r = requests.get(url, headers=_headers)
    assert r.status_code == 200
    group_raw = json.loads(r.content)['groups'][3:]
    group_category_raw = group_raw[0]['group']
    group_band_raw = group_raw[1]['group']
    group_category = {
        item['title']: {'gid': item['gid'], 'containerid': item['containerid']}
        for item in group_category_raw}
    group_band = {
        item['title']: {'gid': item['gid'], 'containerid': item['containerid']}
        for item in group_band_raw}
    return group_band, group_category


def get_hotWeibos(title: str = '24小时榜', num=100):
    """
    获取不同类别或时段的热门微博

    title:from API get_allGroups
    num:MAX=400
    return: list of json-like dict

    //note:id used to get comments as mid,
            user id used to get comments as uid//
    """
    groups, g1 = get_allGroups()
    groups.update(g1)
    gid = groups[title]['gid']
    cid = groups[title]['containerid']
    page = 1

    url = "https://weibo.com/ajax/feed/hottimeline"
    params = {
        "group_id": gid,
        "containerid": cid,
        "extparam": "discover|new_feed",
        'max_id': page
    }

    hotWeibos_raw = []
    if num > 400:
        num = 400
    while len(hotWeibos_raw) < num:
        r = requests.get(url, headers=_headers, params=params)
        assert r.status_code == 200
        hotWeibos_raw += json.loads(r.content)['statuses']
        page += 1
        params['max_id'] = page
    hotWeibos = hotWeibos_raw[:num]

    # dict_keys = ('created_at', 'id', 'mblogid', 'text_raw', 'text',
    #              'reposts_count', 'comments_count', 'attitudes_count')
    # user_keys = ('id', 'screen_name', 'profile_url')

    # def dict_add(d1: dict, d2: dict):
    #     d1.update(d2)
    #     return d1

    # hotWeibos = [dict_add({k: item[k] for k in dict_keys}, {
    #                       'user': {k: item['user'][k] for k in user_keys}}) for item in hotWeibos_raw]
    # for i in range(len(hotWeibos)):
    #     hotWeibos[i]['created_at'] = dt.datetime.strptime(
    #         hotWeibos[i]['created_at'], time_pat).isoformat()
    return hotWeibos


def search_Weibo_raw(keyword: str, searchtype: str = 'weibo', page=1, **search_param) -> BeautifulSoup:
    """
    搜索微博(原始接口)

    搜索类型：
        'weibo','realtime','user','video','topic'
        (微博文章和图片搜索质量不高，故排除 article 和 pic 类型)

    搜索参数：
        video:(optional) xsort=hot(热门),typeall=1(全部),hasvideo=0|1
        weibo:(optional) nodup=1 //不加该参数结果为聚合重复微博

    return:
        html soup

    """
    types = ('weibo', 'realtime', 'user', 'video', 'topic')
    assert searchtype in types

    url = 'https://s.weibo.com/'

    params_dict = {
        "q": keyword,
        'page': page
    }
    if searchtype == 'realtime':
        params_dict.update({"rd": "realtime"})
    if search_param:
        params_dict.update(search_param)

    r = requests.get(url=url+searchtype, headers=_headers, params=params_dict)
    assert r.status_code == 200

    soup = BeautifulSoup(r.text, 'lxml')
    return soup


def search_Weibo_tags(keyword: str, searchtype: str = 'weibo', num=10, **search_param) -> list:
    """
    搜索微博（中间接口）

    搜索类型：
        'weibo','realtime','user','video','topic'
        (微博图片搜索质量不高，故排除 pic 类型)

    搜索参数：
        video:(optional) xsort=hot(热门),typeall=1(全部),hasvideo=0|1
        weibo:(optional) nodup=1 //不加该参数结果为聚合重复微博

    return:
        list of required html tags
    """
    if searchtype == 'weibo' and ('nodup' not in search_param):
        soup = search_Weibo_raw(keyword, searchtype, **search_param)
        if soup.find(class_='m-error') and re.search(r'\d+', soup.find(class_='m-error').text):
            MaxNum = int(
                re.search(r'\d+', soup.find(class_='m-error').text).group(0))
            if num > MaxNum:
                logger = Logger('search_Weibo_tags')
                logger.warning(
                    'Search number is too large,reset to MAX= %d' % MaxNum)
                num = MaxNum

    tags = []
    page = 1

    while len(tags) < num:
        soup = search_Weibo_raw(keyword, searchtype, page, **search_param)
        if searchtype in ('topic', 'user'):
            tags += soup.findAll('div', class_='card')
            if searchtype == 'topic':
                return tags
        else:
            tags += soup.findAll('div', class_='card-wrap', mid=True)
        page += 1
    return tags[:num]


def parse_Weibo_tag(tag: BeautifulSoup) -> dict:
    """
    从每条微博源码提取信息
    type=weibo,realtime,video时调用

    return:json-like dict
            {content:{
                info:{url:,name:},
                time:,
                text:{txt,raw},
                video:{type,url} or None,
                image:url or None,
                forward:url or None,
                }
             act:{
                forward:num,
                comment:{num,mid,uid},
                    //use mid and uid to get comment json//
                like:num,
                }
             }
    """
    content_tag = tag.find(class_='card-feed')
    act_tags = tag.find(class_='card-act').findAll('li')

    info_tag = content_tag.find(class_='info').find('a', class_='name')
    time_tag = content_tag.find(class_='from').next.next.next
    text_tag = content_tag.findAll(
        class_='txt', attrs={'nick-name': re.compile(r'.*')})[-1]

    video = None
    image = None
    forward = None

    media_tag = content_tag.find(class_='media')
    if media_tag:
        if media_tag.find('img'):
            image_tags = media_tag.findAll('img')
            image = [tag.attrs['src'].replace(
                'orj360', 'large') for tag in image_tags]
        else:
            if media_tag.find('video-player'):
                video_str = media_tag.find('video-player').attrs[':options']
                pat = re.compile(
                    r'type:\'(?P<type>.*?)\'.*?src:\'(?P<src>.*?)\'')
                video = pat.search(video_str.replace('\n', '')).groupdict()
                video['src'] = 'https:'+video['src']
            elif media_tag.find('video'):
                video_dict = media_tag.find('video').attrs
                video = {
                    'type': video_dict['x5-video-player-type'],
                    'src': video_dict['src']
                }

    d = {
        'content': {
            'info': {
                'url': 'https:'+info_tag.attrs['href'],
                'name': info_tag.attrs['nick-name']
            },
            'time': time_tag.strip(),
            'text': {
                'text': text_tag.text.strip(),
                'raw': text_tag.contents
            },
            'video': video,
            'image': image,
            'forward': forward
        },
        'act': {
            'forward': act_tags[0].text.strip().replace('转发', '0'),
            'like': act_tags[2].text.strip().replace('赞', '0'),
            'comment': {
                'num': act_tags[1].text.strip().replace('评论', '0'),
                'mid': tag.attrs['mid'],
                'uid': re.search(r'/(\d+)\?', info_tag.attrs['href']).group(1)
            }
        }
    }
    if content_tag.find(class_='card-comment'):
        forward_tag = content_tag.find(
            class_='card-comment').find(class_='func').find(class_='from')
        forward = 'https:'+forward_tag.find('a').attrs['href']
        d['content'].update({'forward': forward})
    return d


def parse_userortopic_tag(tag: BeautifulSoup, type='user') -> dict:
    """
    type:
         用户 user
            key:url,name,num
         话题 topic
            key:name,num
    return:dict
    """
    if type == 'user':
        d = {
            'url': 'https:'+tag.find(class_='name').attrs['href'],
            'name': tag.find(class_='name').text,
            'num': tag.find(class_='s-nobr').text
        }
    else:
        d = re.search(r'>(?P<name>#.*#)<', str(tag)).groupdict()
        d.update(re.search(r'>(?P<num>\d.*讨论.*阅读)<', str(tag)).groupdict())
    return d


def get_comment(uid: 'int|str', mid: 'int|str') -> dict:
    """
    通过 uid 和 mid 获取评论

    最多获取 100 条(硬编码到 count)，获取过多服务器容易拒绝

    return json-like dict
    """
    url = "https://weibo.com/ajax/statuses/buildComments"
    params = {
        "id": mid,
        "is_show_bulletin": "3",
        "count": "100",
        "uid": uid
    }

    r = requests.get(url, params=params, headers=_headers)
    assert r.status_code == 200
    return json.loads(r.content)['data']


def get_uid_from_url(url: str) -> str:
    if re.search(r'\d\?ref', url):
        return re.search(r'/(\d+)\?', url).group(1)
    if re.search(r'/u/', url):
        uid = re.search(r'/(\d+)', url).group(1)
    else:
        req_url = "https://weibo.com/ajax/profile/info"

        if re.search(r'/n/', url):
            params = {
                "screen_name": re.search(r'([^/]*)\Z', url).group(1)
            }
        else:
            params = {
                "custom": re.search(r'([^/]*)\Z', url).group(1)
            }
        r = requests.get(req_url, headers=_headers, params=params)
        assert r.status_code == 200
        uid = json.loads(r.text)['data']['user']['idstr']
    return uid


def get_user_info(uid: 'str|int') -> dict:
    """
    return json-like dict
    """
    url = "https://weibo.com/ajax/profile/info"
    params = {
        "uid": uid
    }

    r = requests.get(url, headers=_headers, params=params)
    assert r.status_code == 200
    return json.loads(r.text)


def get_user_follow(uid: 'str|int', flag: '0|1', num: int) -> list:
    """
    获取粉丝或关注

    flag：1 粉丝 fans/followers；0 关注 followings

    return list of json-like dict
    """
    user_info_dict = get_user_info(uid)
    num_follower = user_info_dict['data']['user']['followers_count']
    num_following = user_info_dict['data']['user']['friends_count']

    page = 1
    url = "https://weibo.com/ajax/friendships/friends"
    params = {
        "page": page,
        "uid": uid
    }

    if flag:
        params.update({"relate": "fans"})
        maxnum = num_follower
    else:
        maxnum = num_following

    logger = Logger('get_user_follow')
    if num > maxnum:
        logger.warning('num too large,reset to MAX: %d' % maxnum)
        num = maxnum

    user_follow_list = []
    while len(user_follow_list) < num:
        r = requests.get(url, headers=_headers, params=params)
        assert r.status_code == 200
        u_list = json.loads(r.content)['users']
        user_follow_list += u_list
        if len(u_list) < 20:
            return user_follow_list
        page += 1
        params['page'] = page
    return user_follow_list[:num]


def get_user_weibo(uid: 'str|int', pages=3) -> list:
    """
    获取用户微博

    return list of json-like
    """
    page = 1
    user_weibo_list = []

    url = "https://weibo.com/ajax/statuses/mymblog"
    params = {
        "uid": uid,
        "page": page
    }

    for page in range(1, pages+1):
        params['page'] = page
        r = requests.get(url, headers=_headers, params=params)
        assert r.status_code == 200
        user_weibo_list += json.loads(r.text)['data']['list']

    return user_weibo_list


def get_feeds(num=30) -> list:
    """
    获取我关注的最新微博

    return list of json-like 
    """
    url = "https://weibo.com/ajax/feed/friendstimeline"
    params = {
        "list_id": "null",
        "count": num
    }

    r = requests.get(url, headers=_headers, params=params)
    assert r.status_code == 200
    return json.loads(r.text)['statuses'][:num]
