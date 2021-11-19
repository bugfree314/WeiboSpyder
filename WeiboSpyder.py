import json
import Weiboutils as WBapi


class Comment:
    """
    use uid and mid to init

    attrs: uid,mid,comments
    """

    def __init__(self, uid, mid) -> None:
        self._uid = uid
        self._mid = mid

    @property
    def raw(self):
        return WBapi.get_comment(self._uid, self._mid)

    @property
    def comment(self):
        return [{
            'uid': c['user']['id'],
            'name':c['user']['name'],
            'created_at':c['created_at'],
            'text':c['text'],
            'text_raw':c['text_raw']
        } for c in self.raw]


class User:
    """
    use uid or user-page-url to init

    attrs: uid,info,shortinfo,fans,follows
            获取 fans 和 follows 为获取全部，量较大时很慢，取决于网速。
            可用 Weiboutils 中的 api 获取指定 num。
    methods: get_Weibo
    """

    def __init__(self, arg: 'int|str') -> None:
        try:
            uid = int(arg)
        except Exception:
            uid = WBapi.get_uid_from_url(arg)
        self.uid = uid
        self.info = self._get_user_info_(self.uid)['data']['user']
        shortinfo_keys = ('id', 'screen_name', 'profile_url',
                          'followers_count', 'friends_count')
        self.shortinfo = {k: self.info[k] for k in shortinfo_keys}

    def get_Weibo(self, pages=3):
        return [Weibo(w) for w in WBapi.get_user_weibo(self.uid, pages)]

    @property
    def fans(self):
        return WBapi.get_user_follow(
            self.uid, 1, self.info['followers_count'])

    @property
    def follows(self):
        return WBapi.get_user_follow(
            self.uid, 0, self.info['friends_count'])

    def _get_user_info_(self, uid):
        return WBapi.get_user_info(uid)


class Weibo:
    """
    attrs: raw,user,createdtime,text,media,retweet
    """

    def __init__(self, weibo_dict: dict) -> None:
        self.raw = weibo_dict

    @property
    def user(self):
        if 'visible' in self.raw.keys():
            url = 'https://weibo.com'+self.raw['user']['profile_url']
        else:
            url = self.raw['content']['info']['url']
        return User(url)

    @property
    def createdtime(self):
        if 'visible' in self.raw.keys():
            return WBapi.dt.datetime.strptime(self.raw['created_at'], WBapi.time_pat).isoformat()
        else:
            return self.raw['content']['time']

    @property
    def text(self):
        if 'visible' not in self.raw.keys():
            return self.raw['content']['text']
        else:
            txt = {
                'text': self.raw['text_raw'],
                'raw': self.raw['text']
            }
            if WBapi.re.search(r'>展开</span>', txt['raw']):
                mblogid = self.raw['mblogid']
                url = "https://weibo.com/ajax/statuses/longtext"
                params = {
                    "id": mblogid
                }

                r = WBapi.requests.get(
                    url, headers=WBapi.get_headers(), params=params)
                assert r.status_code == 200
                txt['raw'] = WBapi.json.loads(
                    r.content)['data']['longTextContent']
            return txt

    @property
    def media(self):
        if 'visible' not in self.raw.keys():
            return {
                'video': self.raw['content']['video'],
                'image': self.raw['content']['image']
            }
        else:
            media_dict = {
                'video': [],
                'image': ['https://wx1.sinaimg.cn/large/'+imgid+'.jpg' for imgid in self.raw['pic_ids']]
            }
            if 'url_struct' in self.raw.keys():
                long_url = self.raw['url_struct'][0]['long_url']
                m = WBapi.re.search(r'fid=(\d+:\d+)', long_url)
                if m:
                    video_id = m.group(1)
                else:
                    return media_dict
                url = "https://weibo.com/tv/api/component"
                params = {
                    "data": "{\"Component_Play_Playinfo\":{\"oid\":\""+video_id+"\"}}",
                }
                headers_dict = {
                    "Referer": "https://weibo.com/tv/show/"+video_id+"?from=old_pc_videoshow"
                }
                headers_dict.update(WBapi.get_headers())
                r = WBapi.requests.post(
                    url, params=params, headers=headers_dict)
                assert r.status_code == 200
                content_dict = WBapi.json.loads(r.content)

                def has_url(d):
                    return ('data' in d) and (isinstance(d['data'], dict)) and ('Component_Play_Playinfo' in d['data']) and (isinstance(d['data']['Component_Play_Playinfo'], dict)) and ('urls' in d['data']['Component_Play_Playinfo'])

                if has_url(content_dict):
                    media_dict['video'] = content_dict['data']['Component_Play_Playinfo']['urls']

            return media_dict

    @property
    def retweet(self):
        fid = None
        if 'visible' not in self.raw.keys():
            if self.raw['content']['forward']:
                fid = WBapi.re.search(
                    r'/([^/]*)\?', self.raw['content']['forward']).group(1)
        else:
            if 'retweeted_status' in self.raw.keys():
                fid = self.raw['retweeted_status']['mblogid']

        if fid:
            url = "https://weibo.com/ajax/statuses/show"
            params = {
                "id": fid
            }

            r = WBapi.requests.get(
                url, params=params, headers=WBapi.get_headers())
            assert r.status_code == 200
            return Weibo(WBapi.json.loads(r.content))
        else:
            return None

    @property
    def comment(self):
        if 'visible' not in self.raw.keys():
            return Comment(self.raw['act']['comment']['uid'], self.raw['act']['comment']['mid'])
        else:
            return Comment(self.raw['user']['id'], self.raw['mid'])

    @property
    def statistic(self):
        if 'visible' in self.raw.keys():
            return {
                'forward': self.raw['reposts_count'],
                'comment': self.raw['comments_count'],
                'like': self.raw['attitudes_count']
            }
        else:
            return {
                'forward': self.raw['act']['forward'],
                'comment': self.raw['act']['comment']['num'],
                'like': self.raw['act']['like']
            }


class WeiboSpyder:
    """
    need cookies to init

    methods:
    get_allGroups
    get_topicband
    get_hotband
    get_hotWeibos
    search_Weibo
    """

    def __init__(self, cookies: str) -> None:
        WBapi.set_cookies(cookies)
        WBapi.set_headers()

    @property
    def allGroups(self):
        """
        获取分组

        return a dict:
            key:value --> title:{'gid','containerid'}
        """
        band, cat = WBapi.get_allGroups()
        band.update(cat)
        return band

    @property
    def topicband(self):
        """
        话题榜

        return a list of dict:
            key:topic,claim:{uid,user},mention,read,summary,category,mid
        """
        return WBapi.get_topicband()

    @property
    def hotband(self):
        """
        热搜榜

        return a tuple of dict:
            0. hotgov:
                dict:mid,word,url
            1. band_list:
                list of dict:
                    key:word,category,num,mid,onboard_time
        """
        return WBapi.get_hotband()

    def hotWeibos(self, title: str = '24小时榜', num=100):
        """
        获取不同类别或时段的热门微博

        title:from API get_allGroups
        num:MAX=400

        return list of Weibo:
        """
        return [Weibo(w) for w in WBapi.get_hotWeibos(title, num)]

    def search(self, keyword: str, searchtype: str = 'weibo', num=10, **search_param):
        """
        搜索微博

        搜索类型：
            'weibo','realtime','user','video','topic'
            (微博图片搜索质量不高，故排除 pic 类型)

        搜索参数：
            video:(optional) xsort=hot(热门),typeall=1(全部),hasvideo=0|1
            weibo:(optional) nodup=1 //不加该参数结果为聚合重复微博

        return:list of searchtype
        """
        tags = WBapi.search_Weibo_tags(
            keyword, searchtype, num, **search_param)
        if searchtype == 'user':
            return [User(u['url']) for u in [WBapi.parse_userortopic_tag(t, searchtype) for t in tags]]
        elif searchtype == 'topic':
            return [WBapi.parse_userortopic_tag(t, searchtype) for t in tags]
        else:
            return [Weibo(w) for w in [WBapi.parse_Weibo_tag(t) for t in tags]]
