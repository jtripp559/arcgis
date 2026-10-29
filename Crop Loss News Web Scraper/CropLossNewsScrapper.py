# pip install gdeltdoc
# conda install requests
# conda install bs4
# conda install gensim
# conda install nltk
# pip install inltk

# required by inltk:
# conda install scikit-learn
# conda install pydantic
# conda install typing_extensions
# conda install googletrans


"""
@inproceedings{arora-2020-inltk,
    title = "i{NLTK}: Natural Language Toolkit for Indic Languages",
    author = "Arora, Gaurav",
    booktitle = "Proceedings of Second Workshop for NLP Open Source Software (NLP-OSS)",
    month = nov,
    year = "2020",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://www.aclweb.org/anthology/2020.nlposs-1.10",
    doi = "10.18653/v1/2020.nlposs-1.10",
    pages = "66--71",
    abstract = "We present iNLTK, an open-source NLP library consisting of pre-trained language models and out-of-the-box support for Data Augmentation, Textual Similarity, Sentence Embeddings, Word Embeddings, Tokenization and Text Generation in 13 Indic Languages. By using pre-trained models from iNLTK for text classification on publicly available datasets, we significantly outperform previously reported results. On these datasets, we also show that by using pre-trained models and data augmentation from iNLTK, we can achieve more than 95{\%} of the previous best performance by using less than 10{\%} of the training data. iNLTK is already being widely used by the community and has 40,000+ downloads, 600+ stars and 100+ forks on GitHub. The library is available at https://github.com/goru001/inltk.",
"""


from gdeltdoc import GdeltDoc, Filters
import pandas as pd
# Url interactions
import requests
from bs4 import BeautifulSoup

# Use JSON for settings
import json

# Natural language processing - ENGLISH
# from gensim.summarization import keywords

# Natural language processing
import nltk  # Import the nltk library
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
# Indian NLP
from inltk.inltk import setup as isetup
from inltk.inltk import tokenize as itokenize
# from inltk.inltk import remove_stopwords as iremove_stopwords

from googletrans import Translator



# Install NLTK and download necessary resources (e.g., for Spanish)
# nltk.download('punkt')  # Download tokenization data
# nltk.download('stopwords')  # Download stopwords data
# nltk.download('averaged_perceptron_tagger')  # Download POS tagging data
# nltk.download('indian')
# nltk.download('punkt', lang='hi')

inltk_languages = {
    "Hindi": "hi",
    "Punjabi": "pa",
    "Gujarati": "gu",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Oriya": "or",
    "Marathi": "mr",
    "Bengali": "bn",
    "Tamil": "ta",
    "Urdu": "ur",
    "Nepali": "ne",
    "Sanskrit": "sa",
    "Telugu": "te"
}
#    "English": "en",   # use nltk for English

# print(inltk_supported_languages)
# Note: You need to run setup('<code-of-language>') when you use a language for the FIRST TIME ONLY. This will download all the necessary models required to do inference for that language.
# for language, code in inltk_languages.items():
#    isetup(code)

# isetup("hi")
# isetup("pa")
# isetup("gu")
# isetup("kn")
# isetup("ml")
# isetup("or")
# isetup("mr")
# isetup("bn")
# isetup("ta")
# isetup("ur")
# isetup("ne")
# isetup("sa")
# isetup("te")


# Define a list of supported languages for inltk
inltk_supported_languages = list(inltk_languages.keys())
# Create an empty list to store the articles
all_articles = []

# read keywords from keywords.json file
with open('keywords.json') as json_file:
    all_keywords = json.load(json_file)
    keywords = all_keywords['keywords']
    words_of_interest = all_keywords['words_of_interest']

# close the file
json_file.close()

# convert all keywords to lower case
keywords = [w.lower() for w in keywords]
words_of_interest = [w.lower() for w in words_of_interest]

# keywords = ["crop loss", "harvest loss"]
start_date = "2023-01-01"
end_date = "2023-07-01"

# Create a translator object
translator = Translator()

def translate(words, dest_language='en'):
    try:
        # Translate the words
        translations = [translator.translate(word, dest=dest_language).text for word in words]
    except:
        return words
    
    # Print the translations
#    print(translations)

    return translations


def search_articles(search_keyword, search_start_date=start_date, search_end_date=end_date):
    articles = None
    f = Filters(
        keyword = search_keyword,
        start_date = search_start_date,
        end_date = search_end_date
    )
    gd = GdeltDoc()
    # Search for articles matching the filters
    articles = gd.article_search(f)
    return articles


def extract_article_text(article_url):
    article_text = None
    try:
        # Send an HTTP GET request to the article URL
        response = requests.get(article_url)

        # Check if the request was successful
        if response.status_code == 200:
            # Parse the HTML content of the page using BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the elements containing the article text (adjust as needed)
            article_text = ""
            # Example: If the article text is within <p> tags, you can do:
            for paragraph in soup.find_all('p'):
                article_text += paragraph.get_text() + "\n"

#            return article_text
#        else:
#            print("Failed to retrieve the article content. {response.status_code}")
    except Exception as e:
        None
#        print(f"An error occurred: {str(e)}")
    return article_text


stop_words_dict = {}

def get_stopwords(language):
    if language not in stop_words_dict:
        try:
            stop_words_dict[language] = set(stopwords.words(language.lower()))
        except:
            stop_words_dict[language] = None
    stop_words = stop_words_dict[language]
    return stop_words

def remove_stopwords(tokens, language):
    filtered_tokens = tokens
                
    # Remove empty strings from the list of tokens
#    filtered_tokens = list(filter(None, filtered_tokens))

    # Remove empty strings and short tokens from the list of tokens
    filtered_tokens = list(filter(lambda x: x.strip() and len(x) > 2, filtered_tokens))
    
    stop_words = get_stopwords(language)
    if stop_words:
        filtered_tokens = [token for token in filtered_tokens if token.lower() not in stop_words]
    
    return filtered_tokens

# print(search_articles(keywords[1]))
# # Get a timeline of the number of articles matching the filters
# timeline = gd.timeline_search("timelinevol", f)
# timeline

for keyword in keywords:
    articles = search_articles(keyword)
    # Append the articles to the list
    all_articles.append(articles)

# Combine all the DataFrames into one
combined_articles = pd.concat(all_articles, ignore_index=True)

# Drop duplicate rows based on the 'url' column
combined_articles = combined_articles.drop_duplicates(subset='url')
# Create a new column 'article_text' in the DataFrame to store the extracted text
combined_articles['article_text'] = None
combined_articles['article_keywords'] = None

# Print or process the combined articles
# print(combined_articles)

test_cnt = 0

# Iterate through the rows of the DataFrame
for index, row in combined_articles.iterrows():
    url = row['url']
    url_mobile = row['url_mobile']
    title = row['title']
    seendate = row['seendate']
    socialimage = row['socialimage']
    domain = row['domain']
    language = row['language']
    language_lower = language.lower()
    sourcecountry = row['sourcecountry']
    
    # Call the extract_article_text function and print the result
    article_text = extract_article_text(url)
    if article_text:
#        print(f"Title: {title}")
#        print(f"URL: {url}")
#        print(f"Extracted Article Text:\n{article_text}")
        combined_articles.at[index, 'article_text'] = article_text
        
        try:
            # Check if the language is supported by inltk
            if language in inltk_supported_languages:
                # Tokenize the text
                tokens = itokenize(article_text, inltk_languages[language]) # where text is string in <code-of-language>
            else:
                # Extract keywords from the article text
                # Tokenize the text
                tokens = word_tokenize(article_text, language=language_lower) #'spanish')
                
            #    stop_words = set(stopwords.words(language_lower)) # 'spanish'))
#                filtered_tokens = [word for word in tokens if word.lower() not in stop_words]

            # Remove stopwords
            filtered_tokens = remove_stopwords(tokens, language_lower)
                
            # Remove empty strings from the list of tokens
#            filtered_tokens = list(filter(None, tokens))
            
            # Remove empty strings and short tokens from the list of tokens
#            filtered_tokens = list(filter(lambda x: x.strip() and len(x) > 2, filtered_tokens))
            
            # if a word in filtered_tokens is in words_of_interest, then add it to article_keywords
#            article_keywords = []
#            for word in filtered_tokens:
#                if word in words_of_interest:
#                    article_keywords.append(word)
            
            article_keywords = [word for word in tokens if word.lower() in words_of_interest.lower()]
            # list has no attribute 'lower'
            # how can i make this work?
            
            
            # Perform keyword extraction (you can use other techniques here)
            article_keywords = filtered_tokens[:(10 - len(article_keywords))]  # Example: Take the first 10 tokens as keywords

            combined_articles.at[index, 'article_keywords'] = ', '.join(article_keywords)
            
            test_cnt += 1
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    
    
#        article_keywords = keywords(article_text, words=10, lemmatize=True, split=True)
#        combined_articles.at[index, 'article_keywords'] = ', '.join(article_keywords)
        if test_cnt > 10:
            break
            
#    else:
#        print("No article text extracted.")


# Print the count of rows with 'article_text' not being None
count_with_article_text = combined_articles['article_text'].notna().sum()
print(f"Count of rows with 'article_text' not being None: {count_with_article_text}")

for index, row in combined_articles.iterrows():
    if row['article_keywords']:
        print('Title:', row['title'])
        print('keywords:', row['article_keywords'])
        print(row['url'])
        if row['language'] != 'English':
            print('language:', row['language'])
            translated_keywords = translate(row['article_keywords'])
            if row['article_keywords'] != translated_keywords:
                print('translated keywords:', translated_keywords)
        print()