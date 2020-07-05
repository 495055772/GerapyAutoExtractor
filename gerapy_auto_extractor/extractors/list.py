import itertools
import math
import operator
from loguru import logger
import numpy as np
from collections import defaultdict
from gerapy_auto_extractor.utils.cluster import cluster_dict
from gerapy_auto_extractor.utils.preprocess import preprocess4list
from gerapy_auto_extractor.extractors.base import BaseExtractor
from gerapy_auto_extractor.utils.element import descendants_of_body
from gerapy_auto_extractor.schemas.element import Element

LIST_MIN_NUMBER = 5
LIST_MIN_LENGTH = 8
LIST_MAX_LENGTH = 35
SIMILARITY_THRESHOLD = 0.8


class ListExtractor(BaseExtractor):
    """
    extract list from index page
    """
    
    def __init__(self, min_number=LIST_MIN_NUMBER, min_length=LIST_MIN_LENGTH, max_length=LIST_MAX_LENGTH,
                 similarity_threshold=SIMILARITY_THRESHOLD):
        """
        init list extractor
        """
        super(ListExtractor, self).__init__()
        self.min_number = min_number
        self.min_length = min_length
        self.max_length = max_length
        self.avg_length = (self.min_length + self.max_length) / 2
        self.similarity_threshold = similarity_threshold
    
    def _probability_of_title_with_length(self, length):
        """
        get the probability of title according to length
        import matplotlib.pyplot as plt
        x = np.asarray(range(5, 40))
        y = list_extractor.probability_of_title_with_length(x)
        plt.plot(x, y, 'g', label='m=0, sig=2')
        plt.show()
        :param length:
        :return:
        """
        sigma = 6
        return np.exp(-1 * ((length - self.avg_length) ** 2) / (2 * (sigma ** 2))) / (math.sqrt(2 * np.pi) * sigma)
    
    def _build_clusters(self, element):
        """
        build candidate clusters according to element
        :return:
        """
        descendants_tree = defaultdict(list)
        descendants = descendants_of_body(element)
        for descendant in descendants:
            # if one element does not have enough siblings, it can not become a child of candidate element
            if descendant.number_of_siblings + 1 < self.min_number:
                continue
            # if min length is larger than specified max length, it can not become a child of candidate element
            if descendant.a_descendants_group_text_min_length > self.max_length:
                continue
            # if max length is smaller than specified min length, it can not become a child of candidate element
            if descendant.a_descendants_group_text_max_length < self.min_length:
                continue
            # descendant element must have same siblings which their similarity should not below similarity_threshold
            if descendant.similarity_with_siblings < self.similarity_threshold:
                continue
            descendants_tree[descendant.parent_selector].append(descendant)
        descendants_tree = dict(descendants_tree)
        
        # cut tree, remove parent block
        selectors = sorted(list(descendants_tree.keys()))
        last_selector = None
        for selector in selectors[::-1]:
            # if later selector
            if last_selector and selector and last_selector.startswith(selector):
                del descendants_tree[selector]
            last_selector = selector
        clusters = cluster_dict(descendants_tree)
        return clusters
    
    def _choose_best_cluster(self, clusters):
        """
        use clustering algorithm to choose best cluster from candidate clusters
        :param clusters:
        :return:
        """
        # choose best cluster using score
        clusters_score = defaultdict(dict)
        clusters_score_arg_max = 0
        clusters_score_max = -1
        for cluster_id, cluster in clusters.items():
            # calculate avg_similarity_with_siblings
            clusters_score[cluster_id]['avg_similarity_with_siblings'] = np.mean(
                [element.similarity_with_siblings for element in cluster])
            # calculate number of elements
            clusters_score[cluster_id]['number_of_elements'] = len(cluster)
            # calculate probability of it contains title
            # clusters_score[cluster_id]['probability_of_title_with_length'] = np.mean([
            #     self._probability_of_title_with_length(len(a_descendant.text)) \
            #     for a_descendant in itertools.chain(*[element.a_descendants for element in cluster]) \
            #     ])
            # TODO: add more quota to select best cluster
            clusters_score[cluster_id]['clusters_score'] = \
                clusters_score[cluster_id]['avg_similarity_with_siblings'] \
                * np.log10(clusters_score[cluster_id]['number_of_elements'] + 1) \
                # * clusters_score[cluster_id]['probability_of_title_with_length']
            # get max score arg index
            if clusters_score[cluster_id]['clusters_score'] > clusters_score_max:
                clusters_score_max = clusters_score[cluster_id]['clusters_score']
                clusters_score_arg_max = cluster_id
        logger.debug(f'clusters_score {clusters_score}')
        best_cluster = clusters[clusters_score_arg_max]
        return best_cluster
    
    def _extract_from_cluster(self, cluster):
        """
        extract title and href from best cluster
        :param cluster:
        :return:
        """
        # get best tag path of title
        probabilities_of_title = defaultdict(list)
        for element in cluster:
            descendants = element.a_descendants
            for descendant in descendants:
                path = descendant.path
                descendant_text = descendant.text
                probability_of_title_with_length = self._probability_of_title_with_length(len(descendant_text))
                # probability_of_title_with_descendants = self.probability_of_title_with_descendants(descendant)
                # TODO: add more quota to calculate probability_of_title
                probability_of_title = probability_of_title_with_length
                probabilities_of_title[path].append(probability_of_title)
        # get most probable tag_path
        probabilities_of_title_avg = {k: np.mean(v) for k, v in probabilities_of_title.items()}
        best_path = max(probabilities_of_title_avg.items(), key=operator.itemgetter(1))[0]
        logger.debug(f'best tag path {best_path}')
        
        # extract according to best tag path
        result = []
        for element in cluster:
            descendants = element.a_descendants
            for descendant in descendants:
                path = descendant.path
                if path != best_path:
                    continue
                title = descendant.text
                url = descendant.attrib.get('href')
                if not url:
                    continue
                if url.startswith('//'):
                    url = 'http:' + url
                result.append({
                    'title': title,
                    'url': url
                })
        return result
    
    def process(self, element: Element):
        """
        extract content from html
        :param element:
        :return:
        """
        # preprocess
        preprocess4list(element)
        
        # build clusters
        clusters = self._build_clusters(element)
        
        # choose best cluster
        best_cluster = self._choose_best_cluster(clusters)
        
        # extract result from best cluster
        return self._extract_from_cluster(best_cluster)


list_extractor = ListExtractor()


def extract_list(html):
    """
    extract list from index html
    :return:
    """
    return list_extractor.extract(html)
