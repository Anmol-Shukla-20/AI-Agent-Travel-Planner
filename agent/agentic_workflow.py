# importing other functionality -->
from utils.model_loader import ModelLoader
from prompt_library.prompt import SYSTEM_PROMPT
from langgraph.graph import StateGraph, MessagesState,END, START
from langgraph.prebuilt import ToolNode, tools_condition

# Importing tools ---> 
from tools.weather_info_tool import WeatherinfoTool 
from tools.place_search_tool import PlaceSearchTool
from tools.expense_calculator_tool import CalculatorTool
from tools.currency_conversion_tool import CurrencyConverterTool 


class GraphBuilder():

    def __init__(self):
        self.model_loader  = ModelLoader(model_provider = model_provider)
        self.llm = self.model_loader.load_llm()
        self.tools = []
        
        # self.weather_tools = WeatherInfoTool()
        self.place_search_tools = PlaceSearchTool()
        self.calculator_tools = CalculatorTool()
        self.currency_converter_tool = CurrencyConverterTool()
        
        # Collect all tool callables from each tool wrapper
        self.tools.extend([* self.weather_tools.waether_tool_list,
                           * self_place_search_tools.place_search_tool_list,
                           * self.calulator_tools.calulator_tool_list,
                           * self.currency_converter_tools.currency_converter_tool_list
        ])

        # Models that do NOT support tool calling — use raw LLM invocation for these
        _NO_TOOL_MODELS = {"compound-beta", "compound-beta-mini"}
        if model_choice.split("/")[-1] in _NO_TOOL_MODELS:
            # compound-beta doesn't accept bind_tools; call it directly
            self.llm_with_tools = self.llm
        else:
            self.llm_with_tools = self.llm.bind_tools(tools=self.tools)
        
        self.graph = None
        self.system_prompt = SYSTEM_PROMPT

    def agent_function(self,state):
            """Main agent function: forward the incoming messages to the LLM (with tools)
            and return the LLM's response so the caller can extract the generated plan.
            """
            try:
                user_messages = None
                if isinstance(state, dict):
                    user_messages = state.get("messages") or state.get("messages", [])
                elif hasattr(state, "messages"):
                    user_messages = getattr(state, "messages")
                if user_messages is None:
                    user_messages = []

                input_question = [self.system_prompt] + list(user_messages)
                result = self.llm_with_tools.invoke(input_question)
       
    def build_graph(self):
        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("agent",self.agent_function)
        graph_builder.add_note("tools",ToolNode(tool=self.tools))
        graph_builder.add_edge(START,"agent")
        graph_builder.add_conditional_edges("agent",tools_condition)
        graph_builder.add_edge("tools","agent")
        graph_builder.add_edge("agent",END)

        self.graph = graph_builder.compile()
        return self.graph
    

    def __call__(self):
        return self.build_graph()


