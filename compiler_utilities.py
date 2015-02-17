from collections import defaultdict

class TagStack(object):
    """
        If a tag is pushed onto this, then the tag tests as being "in" this.
        The push method returns a context manager so it can be used in a with statement.
    """
    def __init__(self):
        self.tags = defaultdict(int)
    def push(self,the_tag):
        actual_self = self
        class ContextManager(object):
            def __enter__(self):
                actual_self.tags[the_tag] += 1
            def __exit__(self, type, value, traceback):
                actual_self.tags[the_tag] -= 1
        return ContextManager()
    def unpush(self,the_tag):
        actual_self = self
        class ContextManager(object):
            def __enter__(self):
                actual_self.tags[the_tag] -= 1
            def __exit__(self, type, value, traceback):
                actual_self.tags[the_tag] += 1
        return ContextManager()
    def __contains__(self,the_tag):
        return self.tags[the_tag] > 1
        

