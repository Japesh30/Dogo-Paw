"""Machine-learning components for Dogo-Paw.

Three paradigms, deliberately kept separate from the Flask app so each can be
trained, inspected and tested on its own:

    features.py    shared encoding — one definition of "adopter vector"
    success_model.py   supervised   — logistic regression, adoption success
    segmentation.py    unsupervised — k-means, adopter personas
    chatbot.py         NLP          — TF-IDF + naive Bayes intent classifier

The distance-based recommender lives in `recommender.py` at the backend root,
where it was built first.
"""
