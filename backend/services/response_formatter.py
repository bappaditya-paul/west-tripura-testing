from __future__ import annotations


CONVERSATIONAL = {
    "en": "Hello! 👋 I’m the West Tripura citizen information assistant. How can I help you?",
    "bn": "নমস্কার! 👋 আমি পশ্চিম ত্রিপুরার নাগরিক তথ্য সহায়ক। কী তথ্য জানতে চান?",
    "bn_en": "Nomoskar! 👋 Ami West Tripura citizen information assistant. Ki information jante chan?",
}

THANKS = {
    "en": "You're welcome! 😊 If you need any West Tripura government information, just ask.",
    "bn": "স্বাগতম! 😊 পশ্চিম ত্রিপুরার সরকারি তথ্য জানতে চাইলে জিজ্ঞাসা করুন।",
    "bn_en": "You're welcome! 😊 West Tripura government information lagle just ask.",
}


class ResponseFormatter:
    def conversational(self, language: str, thanks: bool = False) -> str:
        table = THANKS if thanks else CONVERSATIONAL
        return table.get(language, table["en"])

    def not_verified(self, language: str) -> str:
        if language == "bn":
            return "আমি পশ্চিম ত্রিপুরার সরকারি তথ্যভাণ্ডারে এই তথ্যটি যাচাই করতে পারিনি। অনুগ্রহ করে অফিসিয়াল জেলা পোর্টাল থেকে যাচাই করুন।"
        if language == "bn_en":
            return "Ami West Tripura official database-e ei information verify korte parini. Official district portal theke verify korun."
        return "I couldn't verify this information in the West Tripura government knowledge base. Please verify it through the official district portal."

    def general_disclaimer(self, language: str) -> str:
        if language == "bn":
            return "এটি সাধারণ তথ্য; এটি পশ্চিম ত্রিপুরা জেলার সরকারি তথ্য হিসেবে বিবেচনা করবেন না।"
        if language == "bn_en":
            return "Eta general information; etake West Tripura district-er official information hisebe dhorben na."
        return "This is general information, not verified West Tripura government information."
