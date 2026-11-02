"""
Conversation + ConversationMessage — the parent-teacher Communication Centre.

These map to sgs_support_tickets and sgs_ticket_messages, which the parent
module repurposed: a ticket is a conversation about one child, its messages are
the thread. The ticket vocabulary (ticket_number, category, priority) is left
alone — priority is written as 'MEDIUM' and never read — because renaming live
columns buys nothing.

Declared here rather than imported from the parent module because the two
services are deployed separately and share only the database. Only the columns
faculty actually reads are declared; the parent module owns the rest.

recipient_user_id is the teacher the parent wrote to, as a users_masters
user_id — *not* a teacher_master.teacher_id. The two number different things,
so the bridge in teacher_subjects.user_id_for() is what connects a signed-in
teacher to their conversations.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from app.db.session import Base


class Conversation(Base):
    __tablename__ = "sgs_support_tickets"

    ticket_id         = Column(Integer,     primary_key=True)
    ticket_number     = Column(String,      nullable=True)
    parent_id         = Column(Integer,     nullable=True, index=True)
    student_id        = Column(BigInteger,  nullable=True, index=True)
    subject           = Column(String,      nullable=True)
    category          = Column(String,      nullable=True)
    status            = Column(String,      nullable=True, default="OPEN")
    recipient_name    = Column(String,      nullable=True)
    recipient_user_id = Column(BigInteger,  nullable=True, index=True)
    created_at        = Column(DateTime,    nullable=True)
    updated_at        = Column(DateTime,    nullable=True)


class ConversationMessage(Base):
    __tablename__ = "sgs_ticket_messages"

    message_id  = Column(Integer,  primary_key=True)
    ticket_id   = Column(Integer,  nullable=True, index=True)
    # 'PARENT' or 'TEACHER'. A plain string, not an enum — the parent module
    # writes this column, and an enum here would reject any value it adds.
    sender_type = Column(String,   nullable=True)
    sender_name = Column(String,   nullable=True)
    message     = Column(Text,     nullable=True)
    created_at  = Column(DateTime, nullable=True)
    is_read     = Column(Boolean,  nullable=True, default=False)
