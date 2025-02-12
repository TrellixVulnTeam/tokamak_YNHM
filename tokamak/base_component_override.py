import weakref
from functools import partial
import abc
import inspect
import sys
from future.utils import with_metaclass


from dash._utils import patch_collections_abc
import random

MutableSequence = patch_collections_abc("MutableSequence")


# pylint: disable=no-init,too-few-public-methods
class ComponentRegistry:
    """Holds a registry of the namespaces used by components."""

    registry = set()

    @classmethod
    def get_resources(cls, resource_name):
        resources = []

        for module_name in cls.registry:
            module = sys.modules[module_name]
            resources.extend(getattr(module, resource_name, []))

        return resources


class ComponentMeta(abc.ABCMeta):

    # pylint: disable=arguments-differ
    def __new__(mcs, name, bases, attributes):
        component = abc.ABCMeta.__new__(mcs, name, bases, attributes)
        module = attributes["__module__"].split(".")[0]
        if name == "Component" or module == "builtins":
            # Don't do the base component
            # and the components loaded dynamically by load_component
            # as it doesn't have the namespace.
            return component

        ComponentRegistry.registry.add(module)

        return component


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def _check_if_has_indexable_children(item):
    if not hasattr(item, "children") or (
        not isinstance(item.children, Component)
        and not isinstance(item.children, (tuple, MutableSequence))
    ):

        raise KeyError


class Component(with_metaclass(ComponentMeta, object)):
    class _UNDEFINED(object):
        def __repr__(self):
            return "undefined"

        def __str__(self):
            return "undefined"

    UNDEFINED = _UNDEFINED()

    class _REQUIRED(object):
        def __repr__(self):
            return "required"

        def __str__(self):
            return "required"

    REQUIRED = _REQUIRED()

    __cache = weakref.WeakValueDictionary()



    def __init__(self, **kwargs):
        # print(f"Init called with args: {locals()}")
        # pylint: disable=super-init-not-called
        # del self._valid_wildcard_attributes
        # del self._prop_names
        self.__dict__.update(kwargs)
        # if 'id' in kwargs:
        #
        #     if kwargs['id'] in self.__cache:
        #         for k,v in self.__cache[kwargs['id']].__dict__.items():
        #             setattr(self, k, v)
        #     else:
        #         self.__cache[kwargs['id']] = self
            # globals()[self.id] = self
        _dynamic_props = {}
        try:
            _prop_names = list(self._prop_names)
        except:
            _prop_names = []

        self._valid_wildcard_attributes = ['data-', 'aria-']

        for k, v in list(kwargs.items()):
            # pylint: disable=no-member
            # k = k.replace("_", "-")
            is_serializable = not callable(v)
            if is_serializable:
                if k not in _prop_names:
                    _prop_names.append(k)
                setattr(self, k, v)
            else:
                v = partial(v, self=self)
                _dynamic_props[k] = v

        self._dynamic_props = _dynamic_props
        self._prop_names = tuple(_prop_names)
        if hasattr(self, 'id'):
            self.__cache[self.id] = self

    def to_plotly_json(self):
        # Add normal properties
        props = {
            p: getattr(self, p)
            for p in self._prop_names  # pylint: disable=no-member
            if hasattr(self, p)
        }
        # Add the wildcard properties data-* and aria-*
        props.update(
            {
                k: getattr(self, k)
                for k in self.__dict__
                if any(
                    k.startswith(w)
                    # pylint:disable=no-member
                    for w in self._valid_wildcard_attributes
                )
            }
        )
        as_json = {
            "props": props,
            "type": self._type,  # pylint: disable=no-member
            "namespace": self._namespace,  # pylint: disable=no-member
        }

        return as_json

    # pylint: disable=too-many-branches, too-many-return-statements
    # pylint: disable=redefined-builtin, inconsistent-return-statements
    def _get_set_or_delete(self, id, operation, new_item=None):
        _check_if_has_indexable_children(self)

        # pylint: disable=access-member-before-definition,
        # pylint: disable=attribute-defined-outside-init
        if isinstance(self.children, Component):
            if getattr(self.children, "id", None) is not None:
                # Woohoo! It's the item that we're looking for
                if self.children.id == id:
                    if operation == "get":
                        return self.children
                    elif operation == "set":
                        self.children = new_item
                        return
                    elif operation == "delete":
                        self.children = None
                        return

            # Recursively dig into its subtree
            try:
                if operation == "get":
                    return self.children.__getitem__(id)
                elif operation == "set":
                    self.children.__setitem__(id, new_item)
                    return
                elif operation == "delete":
                    self.children.__delitem__(id)
                    return
            except KeyError:
                pass

        # if children is like a list
        if isinstance(self.children, (tuple, MutableSequence)):
            for i, item in enumerate(self.children):
                # If the item itself is the one we're looking for
                if getattr(item, "id", None) == id:
                    if operation == "get":
                        return item
                    elif operation == "set":
                        self.children[i] = new_item
                        return
                    elif operation == "delete":
                        del self.children[i]
                        return

                # Otherwise, recursively dig into that item's subtree
                # Make sure it's not like a string
                elif isinstance(item, Component):
                    try:
                        if operation == "get":
                            return item.__getitem__(id)
                        elif operation == "set":
                            item.__setitem__(id, new_item)
                            return
                        elif operation == "delete":
                            item.__delitem__(id)
                            return
                    except KeyError:
                        pass

        # The end of our branch
        # If we were in a list, then this exception will get caught
        raise KeyError(id)

    # Magic methods for a mapping interface:
    # - __getitem__
    # - __setitem__
    # - __delitem__
    # - __iter__
    # - __len__


    def __getitem__(self, id):  # pylint: disable=redefined-builtin
        """Recursively find the element with the given ID through the tree of
        children."""

        # A component's children can be undefined, a string, another component,
        # or a list of components.
        return self._get_set_or_delete(id, "get")

    def __setitem__(self, id, item):  # pylint: disable=redefined-builtin
        """Set an element by its ID."""
        return self._get_set_or_delete(id, "set", item)

    def __delitem__(self, id):  # pylint: disable=redefined-builtin
        """Delete items by ID in the tree of children."""
        return self._get_set_or_delete(id, "delete")

    def _traverse(self):
        """Yield each item in the tree."""
        for t in self._traverse_with_paths():
            yield t[1]

    def _traverse_with_paths(self):
        """Yield each item with its path in the tree."""
        children = getattr(self, "children", None)
        children_type = type(children).__name__
        children_id = (
            "(id={:s})".format(children.id)
            if getattr(children, "id", False)
            else ""
        )
        children_string = children_type + " " + children_id

        # children is just a component
        if isinstance(children, Component):
            yield "[*] " + children_string, children
            # pylint: disable=protected-access
            for p, t in children._traverse_with_paths():
                yield "\n".join(["[*] " + children_string, p]), t

        # children is a list of components
        elif isinstance(children, (tuple, MutableSequence)):
            for idx, i in enumerate(children):
                list_path = "[{:d}] {:s} {}".format(
                    idx,
                    type(i).__name__,
                    "(id={:s})".format(i.id)
                    if getattr(i, "id", False)
                    else "",
                )
                yield list_path, i

                if isinstance(i, Component):
                    # pylint: disable=protected-access
                    for p, t in i._traverse_with_paths():
                        yield "\n".join([list_path, p]), t

    def __iter__(self):
        """Yield IDs in the tree of children."""
        for t in self._traverse():
            if isinstance(t, Component) and getattr(t, "id", None) is not None:

                yield t.id

    def __len__(self):
        """Return the number of items in the tree."""
        # TODO - Should we return the number of items that have IDs
        # or just the number of items?
        # The number of items is more intuitive but returning the number
        # of IDs matches __iter__ better.
        length = 0
        if getattr(self, "children", None) is None:
            length = 0
        elif isinstance(self.children, Component):
            length = 1
            length += len(self.children)
        elif isinstance(self.children, (tuple, MutableSequence)):
            for c in self.children:
                length += 1
                if isinstance(c, Component):
                    length += len(c)
        else:
            # string or number
            length = 1
        return length

    def __repr__(self):
        # pylint: disable=no-member
        props_with_values = [
            c for c in self._prop_names if getattr(self, c, None) is not None
        ]

        if any(p != "children" for p in props_with_values):
            props_string = ", ".join(
                "{prop}={value}".format(prop=p, value=repr(getattr(self, p)))
                for p in props_with_values
            )
        else:
            props_string = repr(getattr(self, "children", None))
        return "{type}({props_string})".format(
            type=self._type, props_string=props_string
        )

    # def __getattr__(self, item):
    #
    #     try:
    #         obj = super().__getattribute__(item)
    #         return obj
    #
    #     except Exception as e:
    #         k = item.replace("_", '-')
    #         alt_k = item.replace("-", "_")
    #         if '_dynamic_props' in self.__dict__:
    #             if k in self.__dict__['_dynamic_props']:
    #                 try:
    #                     obj = self.__dict__['_dynamic_props'][k]()
    #                     return obj
    #                 except KeyError:
    #                     raise AttributeError
    #             elif alt_k in self.__dict__['_dynamic_props']:
    #                 try:
    #                     obj = self.__dict__['_dynamic_props'][alt_k]()
    #                     return obj
    #                 except KeyError:
    #                     raise AttributeError
    #
    #         if '_prop_names' in self.__dict__:
    #             if k in self.__dict__['_prop_names']:
    #                 try:
    #                     obj = self.__dict__[k]
    #                     return obj
    #                 except KeyError:
    #                     raise AttributeError
    #             elif alt_k in self.__dict__['_prop_names']:
    #                 try:
    #                     obj = self.__dict__[alt_k]
    #                     return obj
    #                 except KeyError:
    #                     raise AttributeError
    #
    #             elif item in self.__dict__:
    #                 obj = self.__dict__[item]
    #                 return obj
    #             else:
    #                 raise AttributeError
    #         # print(self.__dict__)
    #
    #         print(f"Can't get property {item} ")
    #         raise AttributeError

        #         print(f"[Component.__setattr__]  {e.__class__.__name__} :: {e}")
        #         print(self.__dict__)
        # if item in self.__dict__['_dynamic_props']:
        #     obj = obj(self)


    def __hasattr__(self, item):
        return self.__getattr__(item) is not None
    def __setattr__(self, item, val):
        try:
            if any(item.startswith(prefix) for prefix in self.__dict__['_valid_wildcard_attributes']):
                self.__dict__[item.replace("_", "-")] = val
            else:
                self.__dict__[item] = val
                return
        except:
            pass
        super().__setattr__(item, val)




def _explicitize_args(func):
    # Python 2
    if hasattr(func, "func_code"):
        varnames = func.func_code.co_varnames
    # Python 3
    else:
        varnames = func.__code__.co_varnames

    def wrapper(*args, **kwargs):
        if "_explicit_args" in kwargs.keys():
            raise Exception("Variable _explicit_args should not be set.")
        kwargs["_explicit_args"] = list(
            set(list(varnames[: len(args)]) + [k for k, _ in kwargs.items()])
        )
        if "self" in kwargs["_explicit_args"]:
            kwargs["_explicit_args"].remove("self")
        return func(*args, **kwargs)

    # If Python 3, we can set the function signature to be correct
    if hasattr(inspect, "signature"):
        # pylint: disable=no-member
        new_sig = inspect.signature(wrapper).replace(
            parameters=inspect.signature(func).parameters.values()
        )
        wrapper.__signature__ = new_sig
    return wrapper
if __name__ == '__main__':
    import dash_bootstrap_components as dbc
    foo = dbc.Input(id="foo", value=lambda self: random.randrange(0,1000), **{"aria-footest": "bar"})

